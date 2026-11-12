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

    def admin_login(self) -> None:
        self.enable_mfa()
        self.next_totp_window()
        response = self.login()
        self.assertEqual(response.status_code, 200, response.text)

    def create_invited_user(self, email: str = "new-user@example.test") -> tuple[str, str]:
        response = self.client.post(
            "/v1/auth/admin/invites",
            headers={"Origin": "https://portal.test"},
            json={"email": email},
        )
        self.assertEqual(response.status_code, 200, response.text)
        invite = response.json()
        accepted = self.client.post(
            "/v1/auth/invites/accept",
            headers={"Origin": "https://portal.test"},
            json={"token": invite["invitation_token"], "password": "new user's strong password"},
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        return invite["invite"]["id"], invite["invitation_token"]

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

    def test_api_tokens_are_hash_only_scoped_expiring_and_revocable(self) -> None:
        self.enable_mfa()
        self.next_totp_window()
        web_login = self.login()
        created = self.client.post(
            "/v1/auth/api-tokens",
            headers={"Origin": "https://portal.test"},
            json={
                "name": "  backup integration  ",
                "scopes": ["profile:read", "sessions:read", "sessions:revoke"],
                "expires_in_days": 30,
            },
        )
        self.assertEqual(created.status_code, 200, created.text)
        secret = created.json()["token"]
        token_info = created.json()["api_token"]
        self.assertTrue(secret.startswith("iku_"))
        self.assertEqual(token_info["name"], "backup integration")
        self.assertEqual(token_info["prefix"], secret[:12])
        self.assertEqual(token_info["scopes"], ["profile:read", "sessions:read", "sessions:revoke"])
        self.assertNotIn(secret, created.json()["api_token"].values())

        db = main.connect()
        try:
            stored = db.execute("SELECT * FROM api_tokens WHERE id=?", (token_info["id"],)).fetchone()
            self.assertEqual(stored["token_hash"], main.digest_token(secret))
            self.assertNotEqual(stored["token_hash"], secret)
            self.assertEqual(stored["token_prefix"], secret[:12])
            self.assertEqual(stored["expires_at"] - stored["created_at"], 30 * 24 * 60 * 60)
        finally:
            db.close()

        listed = self.client.get("/v1/auth/api-tokens")
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual([item["id"] for item in listed.json()["tokens"]], [token_info["id"]])
        self.assertNotIn("token_hash", listed.json()["tokens"][0])
        self.assertNotIn("token", listed.json()["tokens"][0])

        headers = {"Authorization": f"Bearer {secret}"}
        profile = self.client.get("/v1/auth/session", headers=headers)
        self.assertEqual(profile.status_code, 200, profile.text)
        self.assertEqual(profile.json()["session"]["client"], "api")
        self.assertEqual(self.client.get("/v1/auth/sessions", headers=headers).status_code, 200)

        self.next_totp_window()
        android = self.login(client="android").json()
        revoke_session = self.client.post(
            "/v1/auth/sessions/revoke",
            headers=headers,
            json={"session_id": android["session"]["id"]},
        )
        self.assertEqual(revoke_session.status_code, 200, revoke_session.text)
        self.assertEqual(revoke_session.json(), {"revoked": True, "current": False})
        self.assertEqual(self.client.get("/v1/auth/session", headers={"Authorization": f"Bearer {android['access_token']}"}).status_code, 401)

        revoked = self.client.post(
            "/v1/auth/api-tokens/revoke",
            headers={"Origin": "https://portal.test"},
            json={"token_id": token_info["id"]},
        )
        self.assertEqual(revoked.status_code, 200, revoked.text)
        self.assertEqual(self.client.get("/v1/auth/session", headers=headers).status_code, 401)
        self.assertEqual(self.client.get("/v1/auth/api-tokens").json()["tokens"], [])

    def test_admin_invite_is_single_use_hash_only_and_creates_normal_user(self) -> None:
        anonymous = self.client.get("/v1/auth/admin/users")
        self.assertEqual(anonymous.status_code, 401)
        self.admin_login()

        missing_origin = self.client.post("/v1/auth/admin/invites", json={"email": "new-user@example.test"})
        self.assertEqual(missing_origin.status_code, 403)
        cannot_assign_admin = self.client.post(
            "/v1/auth/admin/invites",
            headers={"Origin": "https://portal.test"},
            json={"email": "new-user@example.test", "roles": ["admin"]},
        )
        self.assertEqual(cannot_assign_admin.status_code, 422)
        created = self.client.post(
            "/v1/auth/admin/invites",
            headers={"Origin": "https://portal.test"},
            json={"email": "  New-User@example.test "},
        )
        self.assertEqual(created.status_code, 200, created.text)
        payload = created.json()
        token = payload["invitation_token"]
        self.assertTrue(token.startswith("iku_inv_"))
        self.assertEqual(payload["invite"]["roles"], ["user"])

        db = main.connect()
        try:
            stored = db.execute("SELECT * FROM user_invites WHERE id=?", (payload["invite"]["id"],)).fetchone()
            self.assertEqual(stored["token_hash"], main.digest_token(token))
            self.assertNotEqual(stored["token_hash"], token)
        finally:
            db.close()

        listed = self.client.get("/v1/auth/admin/users")
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(listed.json()["invites"][0]["email"], "new-user@example.test")
        self.assertNotIn("token_hash", listed.text)
        self.assertNotIn(token, listed.text)
        self.assertNotIn("password_hash", listed.text)

        accepted = self.client.post(
            "/v1/auth/invites/accept",
            headers={"Origin": "https://portal.test"},
            json={"token": token, "password": "new user's strong password"},
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(accepted.json(), {"status": "account_created", "email": "new-user@example.test"})
        replay = self.client.post(
            "/v1/auth/invites/accept",
            headers={"Origin": "https://portal.test"},
            json={"token": token, "password": "another strong password"},
        )
        self.assertEqual(replay.status_code, 400)
        login = self.client.post("/v1/auth/login", headers={"Origin": "https://portal.test"}, json={
            "email": "new-user@example.test", "password": "new user's strong password", "client": "web",
        })
        self.assertEqual(login.status_code, 200, login.text)
        self.assertEqual(login.json()["user"]["roles"], ["user"])

    def test_reissuing_or_revoking_invite_invalidates_its_token(self) -> None:
        self.admin_login()
        first = self.client.post(
            "/v1/auth/admin/invites", headers={"Origin": "https://portal.test"},
            json={"email": "invited@example.test"},
        ).json()
        second = self.client.post(
            "/v1/auth/admin/invites", headers={"Origin": "https://portal.test"},
            json={"email": "INVITED@example.test"},
        )
        self.assertEqual(second.status_code, 200, second.text)
        self.assertNotEqual(first["invite"]["id"], second.json()["invite"]["id"])

        stale = self.client.post(
            "/v1/auth/invites/accept", headers={"Origin": "https://portal.test"},
            json={"token": first["invitation_token"], "password": "new user's strong password"},
        )
        self.assertEqual(stale.status_code, 400)
        revoked = self.client.post(
            "/v1/auth/admin/invites/revoke", headers={"Origin": "https://portal.test"},
            json={"invite_id": second.json()["invite"]["id"]},
        )
        self.assertEqual(revoked.status_code, 200, revoked.text)
        after_revoke = self.client.post(
            "/v1/auth/invites/accept", headers={"Origin": "https://portal.test"},
            json={"token": second.json()["invitation_token"], "password": "new user's strong password"},
        )
        self.assertEqual(after_revoke.status_code, 400)

    def test_invitation_expires_after_72_hours(self) -> None:
        self.admin_login()
        created = self.client.post(
            "/v1/auth/admin/invites", headers={"Origin": "https://portal.test"},
            json={"email": "expires@example.test"},
        )
        self.assertEqual(created.status_code, 200, created.text)
        self.assertEqual(
            int(datetime.fromisoformat(created.json()["invite"]["expires_at"]).timestamp())
            - int(datetime.fromisoformat(created.json()["invite"]["created_at"]).timestamp()),
            72 * 60 * 60,
        )
        self.clock_offset += 73 * 60 * 60
        expired = self.client.post(
            "/v1/auth/invites/accept", headers={"Origin": "https://portal.test"},
            json={"token": created.json()["invitation_token"], "password": "new user's strong password"},
        )
        self.assertEqual(expired.status_code, 400)

    def test_admin_api_requires_admin_session_not_api_token_or_regular_user(self) -> None:
        self.admin_login()
        token = self.client.post(
            "/v1/auth/api-tokens",
            headers={"Origin": "https://portal.test"},
            json={"name": "profile reader", "scopes": ["profile:read"], "expires_in_days": 30},
        ).json()["token"]
        denied_token = self.client.get("/v1/auth/admin/users", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(denied_token.status_code, 403)

        self.create_invited_user()
        user_login = self.client.post("/v1/auth/login", headers={"Origin": "https://portal.test"}, json={
            "email": "new-user@example.test", "password": "new user's strong password", "client": "web",
        })
        self.assertEqual(user_login.status_code, 200, user_login.text)
        user_client = TestClient(main.app, base_url="https://portal.test")
        user_client.cookies.set(main.SESSION_COOKIE, user_login.cookies.get(main.SESSION_COOKIE))
        try:
            denied = user_client.get("/v1/auth/admin/users")
            self.assertEqual(denied.status_code, 403)
            denied_create = user_client.post(
                "/v1/auth/admin/invites", headers={"Origin": "https://portal.test"},
                json={"email": "forbidden@example.test"},
            )
            self.assertEqual(denied_create.status_code, 403)
        finally:
            user_client.close()

    def test_disabling_user_revokes_sessions_and_reenabling_allows_login(self) -> None:
        self.admin_login()
        self.create_invited_user()
        user_login = self.client.post("/v1/auth/login", headers={"Origin": "https://portal.test"}, json={
            "email": "new-user@example.test", "password": "new user's strong password", "client": "android",
        })
        self.assertEqual(user_login.status_code, 200, user_login.text)
        credentials = user_login.json()
        api_token = "iku_" + "a" * 32
        db = main.connect()
        try:
            user_id = db.execute("SELECT id FROM users WHERE email='new-user@example.test'").fetchone()["id"]
            db.execute(
                "INSERT INTO api_tokens(id,user_id,name,token_prefix,token_hash,scopes_json,created_at,expires_at) "
                "VALUES(?,?,?,?,?,?,?,?)",
                ("b" * 32, user_id, "test token", api_token[:12], main.digest_token(api_token), '["profile:read"]', main.utc_now(), main.utc_now() + 3600),
            )
            db.commit()
        finally:
            db.close()

        db = main.connect()
        try:
            admin_id = db.execute("SELECT id FROM users WHERE email='admin@example.test'").fetchone()["id"]
        finally:
            db.close()
        self_disable = self.client.post(
            "/v1/auth/admin/users/status", headers={"Origin": "https://portal.test"},
            json={"user_id": admin_id, "disabled": True},
        )
        self.assertEqual(self_disable.status_code, 409)
        db = main.connect()
        try:
            target = db.execute("SELECT id FROM users WHERE email='new-user@example.test'").fetchone()
        finally:
            db.close()
        disabled = self.client.post(
            "/v1/auth/admin/users/status", headers={"Origin": "https://portal.test"},
            json={"user_id": target["id"], "disabled": True},
        )
        self.assertEqual(disabled.status_code, 200, disabled.text)
        self.assertEqual(self.client.get("/v1/auth/session", headers={"Authorization": f"Bearer {credentials['access_token']}"}).status_code, 401)
        self.assertEqual(self.client.post("/v1/auth/refresh", json={"refresh_token": credentials["refresh_token"]}).status_code, 401)
        self.assertEqual(self.client.get("/v1/auth/session", headers={"Authorization": f"Bearer {api_token}"}).status_code, 401)
        locked_login = self.client.post("/v1/auth/login", headers={"Origin": "https://portal.test"}, json={
            "email": "new-user@example.test", "password": "new user's strong password", "client": "web",
        })
        self.assertEqual(locked_login.status_code, 401)

        enabled = self.client.post(
            "/v1/auth/admin/users/status", headers={"Origin": "https://portal.test"},
            json={"user_id": target["id"], "disabled": False},
        )
        self.assertEqual(enabled.status_code, 200, enabled.text)
        active_login = self.client.post("/v1/auth/login", headers={"Origin": "https://portal.test"}, json={
            "email": "new-user@example.test", "password": "new user's strong password", "client": "web",
        })
        self.assertEqual(active_login.status_code, 200, active_login.text)

    def test_api_tokens_reject_unknown_scopes_and_cannot_manage_tokens(self) -> None:
        self.enable_mfa()
        self.next_totp_window()
        self.login()
        missing_origin = self.client.post("/v1/auth/api-tokens", json={"name": "integration", "scopes": ["profile:read"]})
        self.assertEqual(missing_origin.status_code, 403)
        invalid_scope = self.client.post(
            "/v1/auth/api-tokens",
            headers={"Origin": "https://portal.test"},
            json={"name": "integration", "scopes": ["admin:*"], "expires_in_days": 30},
        )
        self.assertEqual(invalid_scope.status_code, 422)
        duplicate_scope = self.client.post(
            "/v1/auth/api-tokens",
            headers={"Origin": "https://portal.test"},
            json={"name": "integration", "scopes": ["profile:read", "profile:read"], "expires_in_days": 30},
        )
        self.assertEqual(duplicate_scope.status_code, 422)

        created = self.client.post(
            "/v1/auth/api-tokens",
            headers={"Origin": "https://portal.test"},
            json={"name": "profile reader", "scopes": ["profile:read"], "expires_in_days": 30},
        )
        self.assertEqual(created.status_code, 200, created.text)
        headers = {"Authorization": f"Bearer {created.json()['token']}"}
        self.assertEqual(self.client.get("/v1/auth/session", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/v1/auth/sessions", headers=headers).status_code, 403)
        self.assertEqual(self.client.post("/v1/auth/api-tokens", headers=headers, json={"name": "nested", "scopes": ["profile:read"]}).status_code, 403)
        self.assertEqual(self.client.post("/v1/auth/sessions/revoke", headers=headers, json={"session_id": "a" * 32}).status_code, 403)
        self.assertEqual(self.client.post("/v1/auth/logout", headers=headers).status_code, 204)
        self.assertEqual(self.client.get("/v1/auth/session", headers=headers).status_code, 401)

    def test_api_token_cannot_revoke_another_users_token(self) -> None:
        self.enable_mfa()
        self.next_totp_window()
        self.login()
        created = self.client.post(
            "/v1/auth/api-tokens",
            headers={"Origin": "https://portal.test"},
            json={"name": "admin token", "scopes": ["profile:read"], "expires_in_days": 30},
        )
        now = main.utc_now()
        other_user_id = "other-api-user"
        db = main.connect()
        try:
            db.execute(
                "INSERT INTO users(id,email,password_hash,created_at,updated_at) VALUES(?,?,?,?,?)",
                (other_user_id, "other-api@example.test", main.hash_password("another secure test password"), now, now),
            )
            db.execute("INSERT INTO user_roles(user_id,role) VALUES(?,?)", (other_user_id, "user"))
            db.execute(
                "INSERT INTO api_tokens(id,user_id,name,token_prefix,token_hash,scopes_json,created_at,expires_at) VALUES(?,?,?,?,?,?,?,?)",
                ("c" * 32, other_user_id, "other token", "iku_other00", main.digest_token("iku_other_private_value"), '["profile:read"]', now, now + 3600),
            )
            db.commit()
        finally:
            db.close()
        response = self.client.post(
            "/v1/auth/api-tokens/revoke",
            headers={"Origin": "https://portal.test"},
            json={"token_id": "c" * 32},
        )
        self.assertEqual(response.status_code, 404)
        still_valid = self.client.get("/v1/auth/session", headers={"Authorization": f"Bearer {created.json()['token']}"})
        self.assertEqual(still_valid.status_code, 200)

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
