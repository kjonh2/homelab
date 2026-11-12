import os
import base64
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID

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

    def test_android_logout_revokes_session_and_refresh_family(self) -> None:
        self.enable_mfa()
        self.next_totp_window()
        issued = self.login(client="android").json()
        self.clock_offset += main.ACCESS_TOKEN_TTL + 1
        logged_out = self.client.post("/v1/auth/logout", headers={
            "Authorization": f"Bearer {issued['access_token']}",
        }, json={"refresh_token": issued["refresh_token"]})
        self.assertEqual(logged_out.status_code, 204)
        session = self.client.get("/v1/auth/session", headers={
            "Authorization": f"Bearer {issued['access_token']}",
        })
        self.assertEqual(session.status_code, 401)
        refresh = self.client.post("/v1/auth/refresh", json={"refresh_token": issued["refresh_token"]})
        self.assertEqual(refresh.status_code, 401)

    def test_session_manager_lists_sessions_and_revokes_android_token_family(self) -> None:
        self.enable_mfa()
        self.next_totp_window()
        web_login = self.login()
        web_session_id = web_login.json()["session"]["id"]
        self.next_totp_window()
        android = self.login(client="android").json()

        listed = self.client.get("/v1/auth/sessions")
        self.assertEqual(listed.status_code, 200, listed.text)
        records = listed.json()["sessions"]
        self.assertEqual({item["id"] for item in records}, {web_session_id, android["session"]["id"]})
        self.assertEqual([item["id"] for item in records if item["current"]], [web_session_id])

        missing_origin = self.client.post("/v1/auth/sessions/revoke", json={"session_id": android["session"]["id"]})
        self.assertEqual(missing_origin.status_code, 403)
        still_active = self.client.get("/v1/auth/session", headers={"Authorization": f"Bearer {android['access_token']}"})
        self.assertEqual(still_active.status_code, 200)

        revoked = self.client.post(
            "/v1/auth/sessions/revoke",
            headers={"Origin": "https://portal.test"},
            json={"session_id": android["session"]["id"]},
        )
        self.assertEqual(revoked.status_code, 200, revoked.text)
        self.assertEqual(revoked.json(), {"revoked": True, "current": False})
        self.assertEqual(self.client.get("/v1/auth/session", headers={"Authorization": f"Bearer {android['access_token']}"}).status_code, 401)
        self.assertEqual(self.client.post("/v1/auth/refresh", json={"refresh_token": android["refresh_token"]}).status_code, 401)
        remaining = self.client.get("/v1/auth/sessions").json()["sessions"]
        self.assertEqual([item["id"] for item in remaining], [web_session_id])

    def test_session_manager_cannot_revoke_another_users_session(self) -> None:
        self.enable_mfa()
        self.next_totp_window()
        admin_login = self.login()
        admin_session_id = admin_login.json()["session"]["id"]
        now = main.utc_now()
        other_user_id = "other-user"
        db = main.connect()
        try:
            db.execute(
                "INSERT INTO users(id,email,password_hash,created_at,updated_at) VALUES(?,?,?,?,?)",
                (other_user_id, "other@example.test", main.hash_password("another secure test password"), now, now),
            )
            db.execute("INSERT INTO user_roles(user_id,role) VALUES(?,?)", (other_user_id, "user"))
            user = db.execute("SELECT * FROM users WHERE id=?", (other_user_id,)).fetchone()
            issued = main.issue_session(db, user, "web", "other-browser", "127.0.0.1")
            db.commit()
        finally:
            db.close()
        other_client = TestClient(main.app, base_url="https://portal.test")
        other_client.cookies.set(main.SESSION_COOKIE, issued["_cookie_token"])
        try:
            response = other_client.post(
                "/v1/auth/sessions/revoke",
                headers={"Origin": "https://portal.test"},
                json={"session_id": admin_session_id},
            )
            self.assertEqual(response.status_code, 404)
            self.assertEqual(self.client.get("/v1/auth/session").status_code, 200)
        finally:
            other_client.close()

    def test_firebase_exchange_requires_admin_totp_and_issues_iku_tokens(self) -> None:
        self.enable_mfa()
        self.next_totp_window()
        claims = {
            "sub": "firebase-user-1",
            "email": "admin@example.test",
            "email_verified": True,
            "firebase": {"sign_in_provider": "google.com"},
        }
        with patch.object(main, "verify_firebase_id_token", return_value=claims):
            challenge = self.client.post("/v1/auth/firebase/exchange", json={
                "id_token": "x" * 120,
                "device_name": "Redmi Note 11",
            })
            self.assertEqual(challenge.status_code, 428)
            code = main.totp_at(self.mfa_secret, main.totp_counter(self.mfa_secret))
            response = self.client.post("/v1/auth/firebase/exchange", json={
                "id_token": "x" * 120,
                "totp_code": code,
                "device_name": "Redmi Note 11",
            })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["user"]["roles"], ["admin"])
        self.assertEqual(response.json()["session"]["client"], "android")
        self.assertTrue(response.json()["access_token"])
        self.assertTrue(response.json()["refresh_token"])

    def test_firebase_exchange_refuses_admin_before_totp_is_enabled(self) -> None:
        claims = {
            "sub": "firebase-user-1",
            "email": "admin@example.test",
            "email_verified": True,
            "firebase": {"sign_in_provider": "google.com"},
        }
        with patch.object(main, "verify_firebase_id_token", return_value=claims):
            response = self.client.post("/v1/auth/firebase/exchange", json={"id_token": "x" * 120})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "mfa_setup_required")

    def test_firebase_exchange_will_not_provision_unknown_accounts(self) -> None:
        claims = {
            "sub": "new-firebase-user",
            "email": "unknown@example.test",
            "email_verified": True,
            "firebase": {"sign_in_provider": "google.com"},
        }
        with patch.object(main, "verify_firebase_id_token", return_value=claims):
            response = self.client.post("/v1/auth/firebase/exchange", json={"id_token": "x" * 120})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "invalid_credentials")

    def test_unknown_firebase_key_does_not_force_unbounded_certificate_fetches(self) -> None:
        now = main.utc_now()
        with (
            patch.object(main, "FIREBASE_CERTS", {"known": object()}),
            patch.object(main, "FIREBASE_CERTS_EXPIRES_AT", now + 600),
            patch.object(main, "FIREBASE_LAST_FORCED_REFRESH_AT", now),
            patch("app.main.urlopen") as fetch,
        ):
            cached = main.firebase_certificates(force_refresh=True)
        self.assertIn("known", cached)
        fetch.assert_not_called()

    def test_firebase_id_token_verifies_signature_project_and_verified_email(self) -> None:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = main.utc_now()
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Firebase test key")])
        cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(timezone.utc) - timedelta(minutes=1))
            .not_valid_after(datetime.now(timezone.utc) + timedelta(hours=1))
            .sign(key, hashes.SHA256())
        )
        claims = {
            "aud": "local-44782",
            "iss": "https://securetoken.google.com/local-44782",
            "sub": "firebase-user-1",
            "email": "admin@example.test",
            "email_verified": True,
            "iat": now,
            "exp": now + 3600,
            "auth_time": now,
            "firebase": {"sign_in_provider": "google.com"},
        }
        encode = lambda value: base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode()).rstrip(b"=").decode()
        head = encode({"alg": "RS256", "kid": "test-key", "typ": "JWT"})
        payload = encode(claims)
        signed = f"{head}.{payload}".encode("ascii")
        signature = key.sign(signed, padding.PKCS1v15(), hashes.SHA256())
        token = f"{head}.{payload}." + base64.urlsafe_b64encode(signature).rstrip(b"=").decode()

        with patch.dict(os.environ, {"IKU_FIREBASE_PROJECT_ID": "local-44782"}), patch.object(
            main, "firebase_certificates", return_value={"test-key": cert}
        ):
            verified = main.verify_firebase_id_token(token)
            self.assertEqual(verified["sub"], "firebase-user-1")
            bad_claims = dict(claims, aud="another-project")
            bad_payload = encode(bad_claims)
            bad_signed = f"{head}.{bad_payload}".encode("ascii")
            bad_token = f"{head}.{bad_payload}." + base64.urlsafe_b64encode(
                key.sign(bad_signed, padding.PKCS1v15(), hashes.SHA256())
            ).rstrip(b"=").decode()
            with self.assertRaises(main.HTTPException) as caught:
                main.verify_firebase_id_token(bad_token)
            self.assertEqual(caught.exception.status_code, 401)

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
