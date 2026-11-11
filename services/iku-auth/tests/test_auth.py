import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app import main


class AuthServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        main.DB_PATH = root / "auth.sqlite3"
        self.bootstrap_token = "b" * 48
        self.bootstrap_file = root / "bootstrap"
        self.bootstrap_file.write_text(self.bootstrap_token, encoding="utf-8")
        self.totp_key_file = root / "totp.key"
        self.totp_key_file.write_text(main.Fernet.generate_key().decode("ascii"), encoding="ascii")
        self.env = patch.dict(os.environ, {
            "IKU_AUTH_BOOTSTRAP_TOKEN_FILE": str(self.bootstrap_file),
            "IKU_AUTH_TOTP_KEY_FILE": str(self.totp_key_file),
            "IKU_AUTH_ALLOWED_ORIGINS": "https://portal.test",
        })
        self.env.start()
        main.init_db()
        self.client = TestClient(main.app, base_url="https://portal.test")
        self.clock_offset = 0
        self.clock_patch = patch.object(main, "utc_now", side_effect=lambda: int(__import__("time").time()) + self.clock_offset)
        self.clock_patch.start()
        self.mfa_secret = self.bootstrap_admin()

    def tearDown(self) -> None:
        self.clock_patch.stop()
        self.env.stop()
        self.client.close()
        self.temp.cleanup()

    def bootstrap_admin(self) -> str:
        response = self.client.post("/v1/auth/bootstrap", headers={"Origin": "https://portal.test"}, json={
            "token": self.bootstrap_token,
            "email": "admin@example.test",
            "password": "correct horse battery staple",
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "mfa_setup_required")
        self.recovery_codes = response.json()["recovery_codes"]
        return response.json()["totp_secret"]

    def enable_mfa(self) -> str:
        code = main.totp_at(self.mfa_secret, main.totp_counter(self.mfa_secret))
        response = self.client.post("/v1/auth/bootstrap/verify-mfa", headers={"Origin": "https://portal.test"}, json={
            "token": self.bootstrap_token,
            "email": "admin@example.test",
            "code": code,
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "bootstrap_complete")
        return code

    def login(self, client: str = "web", with_code: bool = True):
        body = {
            "email": "ADMIN@example.test",
            "password": "correct horse battery staple",
            "client": client,
            "device_name": "test-client",
        }
        if with_code:
            body["totp_code"] = main.totp_at(self.mfa_secret, main.totp_counter(self.mfa_secret))
        headers = {"Origin": "https://portal.test"} if client == "web" else {}
        return self.client.post("/v1/auth/login", headers=headers, json=body)

    def next_totp_window(self) -> None:
        self.clock_offset += 30

    def test_admin_bootstrap_requires_and_enables_totp_once(self) -> None:
        response = self.client.post("/v1/auth/bootstrap", headers={"Origin": "https://portal.test"}, json={
            "token": self.bootstrap_token,
            "email": "admin@example.test",
            "password": "correct horse battery staple",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["totp_secret"], self.mfa_secret)

        self.enable_mfa()
        response = self.client.post("/v1/auth/bootstrap/verify-mfa", headers={"Origin": "https://portal.test"}, json={
            "token": self.bootstrap_token,
            "email": "admin@example.test",
            "code": "000000",
        })
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.login(with_code=False).status_code, 428)

    def test_web_login_sets_secure_cookie_session_and_logout_revokes_it(self) -> None:
        self.enable_mfa()
        self.next_totp_window()
        response = self.login()
        self.assertEqual(response.status_code, 200, response.text)
        cookie = response.headers["set-cookie"].lower()
        self.assertIn("httponly", cookie)
        self.assertIn("secure", cookie)
        self.assertIn("samesite=strict", cookie)
        session = self.client.get("/v1/auth/session")
        self.assertEqual(session.status_code, 200, session.text)
        self.assertEqual(session.json()["user"]["roles"], ["admin"])
        self.assertTrue(session.json()["user"]["mfa_enabled"])

        logged_out = self.client.post("/v1/auth/logout", headers={"Origin": "https://portal.test"})
        self.assertEqual(logged_out.status_code, 204)
        self.assertEqual(self.client.get("/v1/auth/session").status_code, 401)

    def test_android_refresh_rotation_and_reuse_revokes_token_family(self) -> None:
        self.enable_mfa()
        self.next_totp_window()
        response = self.login(client="android")
        self.assertEqual(response.status_code, 200, response.text)
        original = response.json()
        self.assertEqual(original["token_type"], "Bearer")
        self.assertNotIn("set-cookie", response.headers)

        checked = self.client.get("/v1/auth/session", headers={"Authorization": f"Bearer {original['access_token']}"})
        self.assertEqual(checked.status_code, 200)

        rotated = self.client.post("/v1/auth/refresh", json={
            "refresh_token": original["refresh_token"], "device_name": "test-client",
        })
        self.assertEqual(rotated.status_code, 200, rotated.text)
        self.assertNotEqual(rotated.json()["refresh_token"], original["refresh_token"])
        replay = self.client.post("/v1/auth/refresh", json={"refresh_token": original["refresh_token"]})
        self.assertEqual(replay.status_code, 401)
        revoked = self.client.get("/v1/auth/session", headers={"Authorization": f"Bearer {rotated.json()['access_token']}"})
        self.assertEqual(revoked.status_code, 401)

    def test_login_origin_and_attempt_limits(self) -> None:
        self.enable_mfa()
        self.next_totp_window()
        missing_origin = self.client.post("/v1/auth/login", json={
            "email": "admin@example.test", "password": "wrong password", "client": "web",
        })
        self.assertEqual(missing_origin.status_code, 403)

        with patch.object(main, "LOGIN_FAILURE_LIMIT", 1):
            failure = self.client.post("/v1/auth/login", headers={"Origin": "https://portal.test"}, json={
                "email": "admin@example.test", "password": "wrong password", "client": "web",
            })
            self.assertEqual(failure.status_code, 401)
            limited = self.client.post("/v1/auth/login", headers={"Origin": "https://portal.test"}, json={
                "email": "admin@example.test", "password": "correct horse battery staple", "client": "web",
            })
            self.assertEqual(limited.status_code, 429)

    def test_validation_errors_do_not_echo_submitted_password(self) -> None:
        password = "s" * 1025
        response = self.client.post("/v1/auth/login", headers={"Origin": "https://portal.test"}, json={
            "email": "admin@example.test", "password": password,
        })
        self.assertEqual(response.status_code, 422)
        self.assertNotIn(password, response.text)


if __name__ == "__main__":
    unittest.main()
