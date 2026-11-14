from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import urlopen
from urllib.parse import quote

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse, RedirectResponse
import jwt

DB_PATH = Path(os.getenv("IKU_AUTH_DB_PATH", "/var/lib/iku-auth/auth.sqlite3"))
SESSION_COOKIE = "iku_session"
WEB_SESSION_TTL = 8 * 60 * 60
ACCESS_TOKEN_TTL = 15 * 60
REFRESH_TOKEN_TTL = 30 * 24 * 60 * 60
API_TOKEN_TTL_DAYS_DEFAULT = 90
API_TOKEN_TTL_DAYS_MAX = 365
API_TOKEN_SCOPES = {"profile:read", "sessions:read", "sessions:revoke"}
FIREBASE_CERTS_URL = "https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com"
LOGIN_WINDOW = 15 * 60
LOGIN_FAILURE_LIMIT = 10
EMAIL_RE = re.compile(r"^[^\s@]{1,64}@[^\s@]{1,190}\.[^\s@]{2,63}$")
PASSWORD_HASHER = PasswordHasher()
ARGON_LOCK = threading.BoundedSemaphore(1)
DUMMY_PASSWORD_HASH = PASSWORD_HASHER.hash("iku-auth-dummy-" + secrets.token_urlsafe(32))
FIREBASE_CERTS_LOCK = threading.Lock()
FIREBASE_CERTS: dict[str, x509.Certificate] = {}
FIREBASE_CERTS_EXPIRES_AT = 0
FIREBASE_LAST_FORCED_REFRESH_AT = 0
OIDC_SIGNING_LOCK = threading.Lock()
OIDC_SCOPES = {"openid", "profile", "email"}
OIDC_ACCESS_TTL = 300
app = FastAPI(title="Iku Auth", docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def security_headers(request: Request, call_next: Any) -> Response:
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > 8192:
        return JSONResponse({"detail": "request_too_large"}, status_code=413, headers={"Cache-Control": "no-store"})
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Pydantic's raw errors can include the submitted value (including passwords).
    details = [{"loc": err.get("loc", []), "msg": err.get("msg", "invalid value"), "type": err.get("type", "value_error")} for err in exc.errors()]
    return JSONResponse({"detail": details}, status_code=422, headers={"Cache-Control": "no-store"})


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class BootstrapInput(StrictModel):
    token: str = Field(min_length=32, max_length=512)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=1024)


class BootstrapVerifyInput(StrictModel):
    token: str = Field(min_length=32, max_length=512)
    email: str = Field(min_length=3, max_length=254)
    code: str = Field(min_length=6, max_length=16)


class LoginInput(StrictModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=1024)
    totp_code: str | None = Field(default=None, min_length=6, max_length=16)
    client: str = Field(default="web", pattern="^(web|android|api)$")
    device_name: str = Field(default="", max_length=100)


class RefreshInput(StrictModel):
    refresh_token: str = Field(min_length=32, max_length=512)
    device_name: str = Field(default="", max_length=100)


class LogoutInput(StrictModel):
    refresh_token: str | None = Field(default=None, min_length=32, max_length=512)


class SessionRevokeInput(StrictModel):
    session_id: str = Field(min_length=32, max_length=64, pattern="^[a-f0-9]+$")


class ApiTokenCreateInput(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    scopes: list[str] = Field(min_length=1, max_length=3)
    expires_in_days: int = Field(default=API_TOKEN_TTL_DAYS_DEFAULT, ge=1, le=API_TOKEN_TTL_DAYS_MAX)


class ApiTokenRevokeInput(StrictModel):
    token_id: str = Field(min_length=32, max_length=64, pattern="^[a-f0-9]+$")


class AdminInviteCreateInput(StrictModel):
    email: str = Field(min_length=3, max_length=254)


class AdminInviteAcceptInput(StrictModel):
    token: str = Field(min_length=32, max_length=512)
    password: str = Field(min_length=12, max_length=1024)


class AdminUserStatusInput(StrictModel):
    user_id: str = Field(min_length=32, max_length=64, pattern="^[a-f0-9]+$")
    disabled: bool


class AdminOidcSubjectInput(StrictModel):
    user_id: str = Field(min_length=32, max_length=64, pattern="^[a-f0-9]+$")
    subject: str = Field(min_length=1, max_length=255, pattern=r"^[\x21-\x7E]+$")


class AdminOidcSubjectClearInput(StrictModel):
    user_id: str = Field(min_length=32, max_length=64, pattern="^[a-f0-9]+$")


class AdminInviteRevokeInput(StrictModel):
    invite_id: str = Field(min_length=32, max_length=64, pattern="^[a-f0-9]+$")


class FirebaseExchangeInput(StrictModel):
    id_token: str = Field(min_length=100, max_length=8192)
    totp_code: str | None = Field(default=None, min_length=6, max_length=16)
    client: str = Field(default="android", pattern="^(web|android)$")
    device_name: str = Field(default="Iku Android", max_length=100)


def utc_now() -> int:
    return int(time.time())


def iso_time(value: int | None = None) -> str:
    return datetime.fromtimestamp(value or utc_now(), timezone.utc).isoformat()


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        os.chmod(DB_PATH.parent, 0o700)
    except OSError:
        pass
    db = sqlite3.connect(DB_PATH, timeout=5)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=5000")
    return db


def init_db() -> None:
    db = connect()
    try:
        db.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                disabled INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS roles (
                name TEXT PRIMARY KEY
            );
            CREATE TABLE IF NOT EXISTS user_roles (
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                role TEXT NOT NULL REFERENCES roles(name),
                PRIMARY KEY(user_id, role)
            );
            CREATE TABLE IF NOT EXISTS mfa_factors (
                user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                totp_ciphertext TEXT,
                enabled INTEGER NOT NULL DEFAULT 0,
                last_counter INTEGER NOT NULL DEFAULT -1,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS recovery_codes (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                code_hash TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                used_at INTEGER
            );
            CREATE INDEX IF NOT EXISTS recovery_codes_user_idx ON recovery_codes(user_id, used_at);
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token_hash TEXT NOT NULL UNIQUE,
                client TEXT NOT NULL,
                device_name TEXT NOT NULL,
                refresh_family TEXT,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                last_seen_at INTEGER NOT NULL,
                revoked_at INTEGER
            );
            CREATE INDEX IF NOT EXISTS sessions_user_idx ON sessions(user_id, revoked_at, expires_at);
            CREATE TABLE IF NOT EXISTS firebase_identities (
                firebase_uid TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                email TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                last_used_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS firebase_identities_user_idx ON firebase_identities(user_id);
            CREATE TABLE IF NOT EXISTS refresh_tokens (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                family_id TEXT NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                device_name TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                consumed_at INTEGER,
                revoked_at INTEGER
            );
            CREATE INDEX IF NOT EXISTS refresh_family_idx ON refresh_tokens(family_id, revoked_at);
            CREATE TABLE IF NOT EXISTS api_tokens (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                token_prefix TEXT NOT NULL DEFAULT '',
                token_hash TEXT NOT NULL UNIQUE,
                scopes_json TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                expires_at INTEGER,
                last_used_at INTEGER,
                revoked_at INTEGER
            );
            CREATE TABLE IF NOT EXISTS user_invites (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL COLLATE NOCASE,
                roles_json TEXT NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                created_by TEXT NOT NULL REFERENCES users(id),
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                accepted_at INTEGER,
                revoked_at INTEGER
            );
            CREATE INDEX IF NOT EXISTS user_invites_pending_idx ON user_invites(email, expires_at, accepted_at, revoked_at);
            CREATE TABLE IF NOT EXISTS audit_events (
                id TEXT PRIMARY KEY,
                user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
                action TEXT NOT NULL,
                result TEXT NOT NULL,
                client TEXT NOT NULL,
                ip TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS audit_user_idx ON audit_events(user_id, created_at);
            CREATE TABLE IF NOT EXISTS login_attempts (
                id TEXT PRIMARY KEY,
                email_key TEXT NOT NULL,
                ip_key TEXT NOT NULL,
                success INTEGER NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS login_attempts_window_idx ON login_attempts(email_key, ip_key, created_at, success);
            CREATE TABLE IF NOT EXISTS auth_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS oidc_authorization_codes (
                code_hash TEXT PRIMARY KEY,
                client_id TEXT NOT NULL,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                redirect_uri TEXT NOT NULL,
                code_challenge TEXT NOT NULL,
                nonce TEXT,
                scope TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                consumed_at INTEGER
            );
            CREATE INDEX IF NOT EXISTS oidc_codes_expiry_idx ON oidc_authorization_codes(expires_at, consumed_at);
            CREATE TABLE IF NOT EXISTS oidc_access_tokens (
                token_hash TEXT PRIMARY KEY,
                client_id TEXT NOT NULL,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                subject TEXT NOT NULL,
                scope TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                revoked_at INTEGER
            );
            CREATE INDEX IF NOT EXISTS oidc_access_expiry_idx ON oidc_access_tokens(expires_at, revoked_at);
            CREATE TABLE IF NOT EXISTS oidc_subject_mappings (
                user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                subject TEXT NOT NULL UNIQUE,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );
            INSERT OR IGNORE INTO roles(name) VALUES ('admin'), ('server'), ('user'), ('api');
            PRAGMA user_version=1;
            """
        )
        token_columns = {row["name"] for row in db.execute("PRAGMA table_info(api_tokens)").fetchall()}
        if "token_prefix" not in token_columns:
            db.execute("ALTER TABLE api_tokens ADD COLUMN token_prefix TEXT NOT NULL DEFAULT ''")
        oidc_token_columns = {row["name"] for row in db.execute("PRAGMA table_info(oidc_access_tokens)").fetchall()}
        if "subject" not in oidc_token_columns:
            db.execute("ALTER TABLE oidc_access_tokens ADD COLUMN subject TEXT")
        db.execute("CREATE INDEX IF NOT EXISTS api_tokens_user_idx ON api_tokens(user_id, revoked_at, expires_at)")
        db.commit()
        try:
            os.chmod(DB_PATH, 0o600)
        except OSError:
            pass
    finally:
        db.close()


@app.on_event("startup")
def startup() -> None:
    init_db()


def read_secret(file_env: str) -> str:
    path = os.getenv(file_env)
    if not path:
        raise HTTPException(status_code=503, detail="secret_not_configured")
    try:
        value = Path(path).read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise HTTPException(status_code=503, detail="secret_not_available") from exc
    if len(value) < 32:
        raise HTTPException(status_code=503, detail="secret_not_available")
    return value


def firebase_certificates(*, force_refresh: bool = False) -> dict[str, x509.Certificate]:
    global FIREBASE_CERTS, FIREBASE_CERTS_EXPIRES_AT, FIREBASE_LAST_FORCED_REFRESH_AT
    now = utc_now()
    if not force_refresh and FIREBASE_CERTS and now < FIREBASE_CERTS_EXPIRES_AT:
        return FIREBASE_CERTS
    with FIREBASE_CERTS_LOCK:
        now = utc_now()
        if force_refresh and FIREBASE_CERTS and now - FIREBASE_LAST_FORCED_REFRESH_AT < 60:
            return FIREBASE_CERTS
        if not force_refresh and FIREBASE_CERTS and now < FIREBASE_CERTS_EXPIRES_AT:
            return FIREBASE_CERTS
        try:
            with urlopen(FIREBASE_CERTS_URL, timeout=4) as response:
                payload = json.loads(response.read(65536))
                cache_control = response.headers.get("Cache-Control", "")
            certs = {kid: x509.load_pem_x509_certificate(pem.encode("ascii")) for kid, pem in payload.items()}
            if not certs:
                raise ValueError("empty certificate response")
        except Exception as exc:
            raise HTTPException(status_code=503, detail="identity_provider_unavailable") from exc
        max_age = re.search(r"(?:^|,)\s*max-age=(\d+)", cache_control, re.IGNORECASE)
        ttl = max(60, min(int(max_age.group(1)) if max_age else 300, 24 * 60 * 60))
        FIREBASE_CERTS = certs
        FIREBASE_CERTS_EXPIRES_AT = now + ttl
        if force_refresh:
            FIREBASE_LAST_FORCED_REFRESH_AT = now
        return certs


def _decode_jwt_part(value: str) -> dict[str, Any]:
    decoded = base64.urlsafe_b64decode(value + "=" * ((4 - len(value) % 4) % 4))
    result = json.loads(decoded)
    if not isinstance(result, dict):
        raise ValueError("JWT part must be an object")
    return result


def verify_firebase_id_token(token: str) -> dict[str, Any]:
    project_id = os.getenv("IKU_FIREBASE_PROJECT_ID", "").strip()
    if not project_id:
        raise HTTPException(status_code=503, detail="identity_provider_not_configured")
    try:
        if len(token) > 8192:
            raise ValueError("token too large")
        header_part, payload_part, signature_part = token.split(".")
        header = _decode_jwt_part(header_part)
        claims = _decode_jwt_part(payload_part)
        kid = header.get("kid")
        if header.get("alg") != "RS256" or not isinstance(kid, str) or not kid or header.get("typ", "JWT") != "JWT":
            raise ValueError("unsupported JWT header")
        certificate = firebase_certificates().get(kid)
        if certificate is None:
            certificate = firebase_certificates(force_refresh=True).get(kid)
        if certificate is None:
            raise ValueError("unknown signing key")
        public_key = certificate.public_key()
        if not isinstance(public_key, rsa.RSAPublicKey):
            raise ValueError("unsupported signing key")
        signature = base64.urlsafe_b64decode(signature_part + "=" * ((4 - len(signature_part) % 4) % 4))
        public_key.verify(signature, f"{header_part}.{payload_part}".encode("ascii"), padding.PKCS1v15(), hashes.SHA256())

        now = utc_now()
        issued_at = claims.get("iat")
        expires_at = claims.get("exp")
        auth_time = claims.get("auth_time")
        uid = claims.get("sub")
        email = claims.get("email")
        firebase_claims = claims.get("firebase")
        if claims.get("aud") != project_id or claims.get("iss") != f"https://securetoken.google.com/{project_id}":
            raise ValueError("wrong issuer or audience")
        if not all(isinstance(value, int) and not isinstance(value, bool) for value in (issued_at, expires_at, auth_time)):
            raise ValueError("invalid timestamps")
        if expires_at <= now or issued_at > now + 300 or auth_time > now + 300 or expires_at - issued_at > 3660:
            raise ValueError("expired or invalid timestamps")
        if not isinstance(uid, str) or not uid or len(uid) > 128:
            raise ValueError("invalid subject")
        if not isinstance(email, str) or claims.get("email_verified") is not True:
            raise ValueError("unverified email")
        if not isinstance(firebase_claims, dict) or firebase_claims.get("sign_in_provider") not in {"google.com", "password"}:
            raise ValueError("unsupported provider")
        claims["email"] = normalize_email(email)
        return claims
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail="invalid_identity_token") from exc


def get_fernet() -> Fernet:
    try:
        return Fernet(read_secret("IKU_AUTH_TOTP_KEY_FILE").encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise HTTPException(status_code=503, detail="encryption_key_invalid") from exc


def hash_password(password: str) -> str:
    with ARGON_LOCK:
        return PASSWORD_HASHER.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        with ARGON_LOCK:
            return PASSWORD_HASHER.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def digest_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_email(value: str) -> str:
    email = value.strip().casefold()
    if not EMAIL_RE.fullmatch(email):
        raise HTTPException(status_code=422, detail="invalid_email")
    return email


def new_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def totp_counter(secret: str, at: int | None = None) -> int:
    return int(at or utc_now()) // 30


def totp_at(secret: str, counter: int) -> str:
    key = base64.b32decode(secret + "=" * ((8 - len(secret) % 8) % 8), casefold=True)
    digest = hmac.new(key, counter.to_bytes(8, "big"), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = (int.from_bytes(digest[offset:offset + 4], "big") & 0x7FFFFFFF) % 1_000_000
    return f"{number:06d}"


def match_totp(secret: str, code: str, after_counter: int = -1) -> int | None:
    if not code.isdigit() or len(code) != 6:
        return None
    current = totp_counter(secret)
    for counter in (current - 1, current, current + 1):
        if counter > after_counter and hmac.compare_digest(totp_at(secret, counter), code):
            return counter
    return None


def fresh_recovery_codes() -> list[str]:
    return [secrets.token_urlsafe(12) for _ in range(10)]


def save_recovery_codes(db: sqlite3.Connection, user_id: str, codes: list[str]) -> None:
    db.execute("DELETE FROM recovery_codes WHERE user_id=?", (user_id,))
    now = utc_now()
    db.executemany(
        "INSERT INTO recovery_codes(id,user_id,code_hash,created_at) VALUES(?,?,?,?)",
        [(secrets.token_hex(16), user_id, digest_token(code), now) for code in codes],
    )


def audit(db: sqlite3.Connection, user_id: str | None, action: str, result: str, client: str, ip: str) -> None:
    db.execute(
        "INSERT INTO audit_events(id,user_id,action,result,client,ip,created_at) VALUES(?,?,?,?,?,?,?)",
        (secrets.token_hex(16), user_id, action, result, client[:32], ip[:80], utc_now()),
    )


def request_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def verify_origin(request: Request, *, required: bool = False) -> None:
    origin = request.headers.get("origin")
    if not origin:
        if required:
            raise HTTPException(status_code=403, detail="origin_required")
        return
    allowed = {item.strip().rstrip("/") for item in os.getenv("IKU_AUTH_ALLOWED_ORIGINS", "").split(",") if item.strip()}
    if not allowed or origin.rstrip("/") not in allowed:
        raise HTTPException(status_code=403, detail="origin_not_allowed")


def bootstrap_token_matches(candidate: str) -> bool:
    expected = read_secret("IKU_AUTH_BOOTSTRAP_TOKEN_FILE")
    return hmac.compare_digest(expected.encode(), candidate.encode())


def is_bootstrap_complete(db: sqlite3.Connection) -> bool:
    row = db.execute("SELECT value FROM auth_state WHERE key='bootstrap_completed'").fetchone()
    return bool(row and row["value"] == "1")


def issue_totp_enrollment(db: sqlite3.Connection, user_id: str, email: str) -> dict[str, Any]:
    factor = db.execute("SELECT * FROM mfa_factors WHERE user_id=?", (user_id,)).fetchone()
    now = utc_now()
    if factor and factor["enabled"]:
        raise HTTPException(status_code=409, detail="mfa_already_enabled")
    if factor and factor["totp_ciphertext"]:
        try:
            secret = get_fernet().decrypt(factor["totp_ciphertext"].encode()).decode("ascii")
        except (InvalidToken, UnicodeDecodeError) as exc:
            raise HTTPException(status_code=503, detail="mfa_secret_unavailable") from exc
    else:
        secret = new_totp_secret()
        ciphertext = get_fernet().encrypt(secret.encode()).decode("ascii")
        db.execute(
            "INSERT INTO mfa_factors(user_id,totp_ciphertext,created_at,updated_at) VALUES(?,?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET totp_ciphertext=excluded.totp_ciphertext,updated_at=excluded.updated_at",
            (user_id, ciphertext, now, now),
        )
    codes = fresh_recovery_codes()
    save_recovery_codes(db, user_id, codes)
    issuer = quote("Iku", safe="")
    label = quote(f"Iku:{email}", safe="")
    uri = f"otpauth://totp/{label}?secret={secret}&issuer={issuer}&algorithm=SHA1&digits=6&period=30"
    return {"totp_secret": secret, "otpauth_uri": uri, "recovery_codes": codes}


def load_user_for_token(db: sqlite3.Connection, request: Request) -> tuple[sqlite3.Row, sqlite3.Row, str] | None:
    bearer = request.headers.get("authorization", "")
    token = bearer[7:].strip() if bearer.lower().startswith("bearer ") else request.cookies.get(SESSION_COOKIE, "")
    if not token:
        return None
    now = utc_now()
    row = db.execute(
        "SELECT s.*,u.email,u.disabled,'session' AS credential_type,'[]' AS scopes_json FROM sessions s JOIN users u ON u.id=s.user_id "
        "WHERE s.token_hash=? AND s.revoked_at IS NULL AND s.expires_at>?",
        (digest_token(token), now),
    ).fetchone()
    if row and not row["disabled"]:
        return row, row, token
    row = db.execute(
        "SELECT t.id,t.user_id,t.name AS device_name,'api' AS client,NULL AS refresh_family,t.created_at,t.expires_at,"
        "COALESCE(t.last_used_at,t.created_at) AS last_seen_at,t.revoked_at,t.token_hash,t.scopes_json,"
        "u.email,u.disabled,'api_token' AS credential_type "
        "FROM api_tokens t JOIN users u ON u.id=t.user_id "
        "WHERE t.token_hash=? AND t.revoked_at IS NULL AND (t.expires_at IS NULL OR t.expires_at>?)",
        (digest_token(token), now),
    ).fetchone()
    if not row or row["disabled"]:
        return None
    return row, row, token


def require_scope(credential: sqlite3.Row, scope: str) -> None:
    if credential["credential_type"] != "api_token":
        return
    try:
        scopes = json.loads(credential["scopes_json"])
    except (TypeError, json.JSONDecodeError):
        scopes = []
    if scope not in scopes:
        raise HTTPException(status_code=403, detail="scope_required")


def require_session_credential(credential: sqlite3.Row) -> None:
    if credential["credential_type"] != "session":
        raise HTTPException(status_code=403, detail="session_required")


def require_admin_session(db: sqlite3.Connection, request: Request) -> sqlite3.Row:
    loaded = load_user_for_token(db, request)
    if not loaded:
        raise HTTPException(status_code=401, detail="not_authenticated")
    current, _, _ = loaded
    require_session_credential(current)
    roles = db.execute("SELECT role FROM user_roles WHERE user_id=?", (current["user_id"],)).fetchall()
    if "admin" not in {row["role"] for row in roles}:
        raise HTTPException(status_code=403, detail="admin_required")
    factor = db.execute("SELECT enabled FROM mfa_factors WHERE user_id=?", (current["user_id"],)).fetchone()
    if not factor or not factor["enabled"]:
        raise HTTPException(status_code=403, detail="mfa_setup_required")
    return current


def issue_session(db: sqlite3.Connection, user: sqlite3.Row, client: str, device_name: str, ip: str) -> dict[str, Any]:
    now = utc_now()
    token = secrets.token_urlsafe(32)
    sid = secrets.token_hex(16)
    family = secrets.token_hex(16) if client == "android" else None
    access_ttl = WEB_SESSION_TTL if client == "web" else ACCESS_TOKEN_TTL
    db.execute(
        "INSERT INTO sessions(id,user_id,token_hash,client,device_name,refresh_family,created_at,expires_at,last_seen_at) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (sid, user["id"], digest_token(token), client, device_name[:100], family, now, now + access_ttl, now),
    )
    roles = [r["role"] for r in db.execute("SELECT role FROM user_roles WHERE user_id=? ORDER BY role", (user["id"],)).fetchall()]
    result: dict[str, Any] = {
        "user": {"id": user["id"], "email": user["email"], "roles": roles},
        "session": {"id": sid, "client": client, "device_name": device_name[:100], "expires_at": iso_time(now + access_ttl)},
    }
    if client == "web":
        result["_cookie_token"] = token
    else:
        refresh = secrets.token_urlsafe(48)
        db.execute(
            "INSERT INTO refresh_tokens(id,user_id,family_id,token_hash,device_name,created_at,expires_at) VALUES(?,?,?,?,?,?,?)",
            (secrets.token_hex(16), user["id"], family, digest_token(refresh), device_name[:100], now, now + REFRESH_TOKEN_TTL),
        )
        result["access_token"] = token
        result["token_type"] = "Bearer"
        result["expires_in"] = access_ttl
        result["refresh_token"] = refresh
    audit(db, user["id"], "auth.login", "success", client, ip)
    return result


def set_session_cookie(response: Response, token: str, ttl: int) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=ttl,
        httponly=True,
        secure=True,
        samesite="strict",
        path="/",
    )


def record_attempt(db: sqlite3.Connection, email: str, ip: str, success: bool) -> None:
    db.execute(
        "INSERT INTO login_attempts(id,email_key,ip_key,success,created_at) VALUES(?,?,?,?,?)",
        (secrets.token_hex(16), digest_token(email), digest_token(ip), int(success), utc_now()),
    )


def login_is_limited(db: sqlite3.Connection, email: str, ip: str) -> bool:
    row = db.execute(
        "SELECT COUNT(*) AS n FROM login_attempts WHERE email_key=? AND ip_key=? AND success=0 AND created_at>?",
        (digest_token(email), digest_token(ip), utc_now() - LOGIN_WINDOW),
    ).fetchone()
    return int(row["n"]) >= LOGIN_FAILURE_LIMIT


def check_totp_or_recovery(db: sqlite3.Connection, user_id: str, code: str) -> bool:
    factor = db.execute("SELECT * FROM mfa_factors WHERE user_id=? AND enabled=1", (user_id,)).fetchone()
    if not factor:
        return False
    try:
        secret = get_fernet().decrypt(factor["totp_ciphertext"].encode()).decode("ascii")
    except (InvalidToken, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=503, detail="mfa_secret_unavailable") from exc
    counter = match_totp(secret, code, int(factor["last_counter"]))
    if counter is not None:
        db.execute("UPDATE mfa_factors SET last_counter=?,updated_at=? WHERE user_id=?", (counter, utc_now(), user_id))
        return True
    code_hash = digest_token(code.strip())
    recovery = db.execute(
        "SELECT id FROM recovery_codes WHERE user_id=? AND code_hash=? AND used_at IS NULL",
        (user_id, code_hash),
    ).fetchone()
    if recovery:
        db.execute("UPDATE recovery_codes SET used_at=? WHERE id=? AND used_at IS NULL", (utc_now(), recovery["id"]))
        return True
    return False


def oidc_settings() -> dict[str, str]:
    issuer = os.getenv("IKU_OIDC_ISSUER", "").rstrip("/")
    client_id = os.getenv("IKU_OIDC_CLIENT_ID", "")
    redirect_uri = os.getenv("IKU_OIDC_REDIRECT_URI", "")
    login_url = os.getenv("IKU_OIDC_LOGIN_URL", "")
    secret_file = os.getenv("IKU_OIDC_CLIENT_SECRET_FILE", "")
    try:
        issuer_parts = urllib.parse.urlsplit(issuer)
        login_parts = urllib.parse.urlsplit(login_url)
        redirect_parts = urllib.parse.urlsplit(redirect_uri)
        issuer_port = issuer_parts.port
        login_port = login_parts.port
        redirect_port = redirect_parts.port
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="oidc_not_configured") from exc
    if (
        issuer_parts.scheme != "https" or not issuer_parts.hostname or issuer_parts.username or issuer_parts.password
        or not issuer_parts.path.startswith("/") or issuer_parts.query or issuer_parts.fragment
        or issuer_port is not None and not 1 <= issuer_port <= 65535
        or not client_id or redirect_parts.scheme != "https" or not redirect_parts.hostname
        or redirect_parts.username or redirect_parts.password or not redirect_parts.path.startswith("/")
        or redirect_parts.query or redirect_parts.fragment
        or redirect_port is not None and not 1 <= redirect_port <= 65535
        or login_parts.scheme != "https" or not login_parts.hostname or login_parts.username or login_parts.password
        or login_parts.hostname.casefold() != issuer_parts.hostname.casefold() or login_port != issuer_port
        or not login_parts.path.startswith("/")
        or login_parts.query or login_parts.fragment
        or not secret_file
    ):
        raise HTTPException(status_code=503, detail="oidc_not_configured")
    return {
        "issuer": issuer,
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "login_url": login_url,
        "secret_file": secret_file,
    }


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def oidc_signing_key() -> rsa.RSAPrivateKey:
    path = DB_PATH.parent / "oidc-signing-key.pem"
    with OIDC_SIGNING_LOCK:
        try:
            key_data = path.read_bytes()
        except FileNotFoundError:
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
            key_data = key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
            temporary = path.with_name(f"{path.name}.{secrets.token_hex(8)}.tmp")
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as key_file:
                key_file.write(key_data)
            temporary.replace(path)
            return key
        except OSError as exc:
            raise HTTPException(status_code=503, detail="oidc_signing_key_unavailable") from exc
        try:
            key = serialization.load_pem_private_key(key_data, password=None)
            if not isinstance(key, rsa.RSAPrivateKey) or key.key_size < 2048:
                raise ValueError("OIDC signing key must be RSA with at least 2048 bits")
            return key
        except (TypeError, ValueError, OSError) as exc:
            raise HTTPException(status_code=503, detail="oidc_signing_key_unavailable") from exc


def oidc_key_id(key: rsa.RSAPrivateKey) -> str:
    public_der = key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return _b64url(hashlib.sha256(public_der).digest()[:16])


def oidc_signed_token(claims: dict[str, Any], key: rsa.RSAPrivateKey, kid: str) -> str:
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": kid, "typ": "JWT"})


def oidc_client_auth(request: Request, fields: dict[str, str], settings: dict[str, str]) -> bool:
    client_id = ""
    client_secret = ""
    authorization = request.headers.get("authorization", "")
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() == "basic" and value:
        try:
            decoded = base64.b64decode(value, validate=True).decode("utf-8")
            client_id, client_secret = decoded.split(":", 1)
        except (ValueError, UnicodeDecodeError):
            return False
    elif scheme:
        return False
    else:
        client_id = fields.get("client_id", "")
        client_secret = fields.get("client_secret", "")
    if not hmac.compare_digest(client_id, settings["client_id"]):
        return False
    try:
        expected_secret = read_secret("IKU_OIDC_CLIENT_SECRET_FILE")
    except HTTPException:
        return False
    return hmac.compare_digest(client_secret.encode("utf-8"), expected_secret.encode("utf-8"))


def oidc_token_error(error: str, status: int = 400) -> JSONResponse:
    return JSONResponse(
        {"error": error},
        status_code=status,
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


def oidc_authorization_error(redirect_uri: str, state: str, error: str) -> RedirectResponse:
    query = {"error": error}
    if state:
        query["state"] = state
    return RedirectResponse(f"{redirect_uri}?{urllib.parse.urlencode(query)}", status_code=302)


def _oidc_login_redirect(request: Request, settings: dict[str, str]) -> RedirectResponse:
    return_to = "/api/auth/oidc/authorize"
    if request.url.query:
        query = urllib.parse.parse_qsl(request.url.query, keep_blank_values=True, max_num_fields=64)
        if request.query_params.get("prompt") == "login":
            query = [(key, value) for key, value in query if key != "prompt"]
        return_to += "?" + urllib.parse.urlencode(query)
    target = settings["login_url"] + "?" + urllib.parse.urlencode({"return_to": return_to})
    return RedirectResponse(target, status_code=302)


@app.get("/v1/auth/oidc/.well-known/openid-configuration")
def oidc_discovery() -> dict[str, Any]:
    settings = oidc_settings()
    base = settings["issuer"]
    return {
        "issuer": base,
        "authorization_endpoint": f"{base}/authorize",
        "token_endpoint": f"{base}/token",
        "userinfo_endpoint": f"{base}/userinfo",
        "jwks_uri": f"{base}/jwks",
        "response_types_supported": ["code"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"],
        "scopes_supported": sorted(OIDC_SCOPES),
        "claims_supported": ["sub", "email", "email_verified", "name", "preferred_username"],
        "grant_types_supported": ["authorization_code"],
        "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"],
        "code_challenge_methods_supported": ["S256"],
        "userinfo_signing_alg_values_supported": ["none"],
    }


@app.get("/v1/auth/oidc/jwks")
def oidc_jwks() -> dict[str, Any]:
    key = oidc_signing_key()
    numbers = key.public_key().public_numbers()
    modulus = numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")
    exponent = numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big")
    return {
        "keys": [{
            "kty": "RSA", "use": "sig", "alg": "RS256", "kid": oidc_key_id(key),
            "n": _b64url(modulus), "e": _b64url(exponent),
        }]
    }


@app.get("/v1/auth/oidc/authorize")
def oidc_authorize(request: Request) -> Response:
    settings = oidc_settings()
    if len(request.url.query) > 8192:
        return JSONResponse({"error": "invalid_request"}, status_code=400)
    for name in ("client_id", "redirect_uri", "response_type", "scope", "state", "nonce", "code_challenge", "code_challenge_method"):
        if len(request.query_params.getlist(name)) > 1:
            return JSONResponse({"error": "invalid_request"}, status_code=400)
    client_id = request.query_params.get("client_id", "")
    redirect_uri = request.query_params.get("redirect_uri", "")
    state = request.query_params.get("state", "")
    scope_items = request.query_params.get("scope", "").split()
    challenge = request.query_params.get("code_challenge", "")
    nonce = request.query_params.get("nonce", "")
    valid_redirect = hmac.compare_digest(client_id, settings["client_id"]) and hmac.compare_digest(redirect_uri, settings["redirect_uri"])
    if not valid_redirect:
        return JSONResponse({"error": "invalid_request"}, status_code=400)
    if (
        request.query_params.get("response_type") != "code"
        or not state or len(state) > 512
        or not scope_items or len(scope_items) != len(set(scope_items))
        or "openid" not in scope_items or any(scope not in OIDC_SCOPES for scope in scope_items)
        or (nonce and len(nonce) > 512)
        or request.query_params.get("code_challenge_method") != "S256"
        or not re.fullmatch(r"[A-Za-z0-9_-]{43,128}", challenge)
        or request.query_params.get("response_mode", "query") != "query"
        or request.query_params.get("prompt", "") not in ("", "none", "login")
    ):
        return oidc_authorization_error(redirect_uri, state, "invalid_request")

    db = connect()
    try:
        session_token = request.cookies.get(SESSION_COOKIE, "")
        user = None
        if session_token:
            user = db.execute(
                "SELECT u.id,u.email FROM sessions s JOIN users u ON u.id=s.user_id "
                "WHERE s.token_hash=? AND s.revoked_at IS NULL AND s.expires_at>? AND u.disabled=0",
                (digest_token(session_token), utc_now()),
            ).fetchone()
        if not user:
            if request.query_params.get("prompt") == "none":
                return oidc_authorization_error(redirect_uri, state, "login_required")
            return _oidc_login_redirect(request, settings)
        if request.query_params.get("prompt") == "login":
            return _oidc_login_redirect(request, settings)

        now = utc_now()
        code = secrets.token_urlsafe(32)
        db.execute("BEGIN IMMEDIATE")
        db.execute("DELETE FROM oidc_authorization_codes WHERE expires_at<=? OR consumed_at IS NOT NULL", (now,))
        db.execute(
            "INSERT INTO oidc_authorization_codes(code_hash,client_id,user_id,redirect_uri,code_challenge,nonce,scope,created_at,expires_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (digest_token(code), settings["client_id"], user["id"], redirect_uri, challenge, nonce or None, " ".join(scope_items), now, now + 180),
        )
        audit(db, user["id"], "auth.oidc.authorize", "success", "oidc", request_ip(request))
        db.commit()
        return RedirectResponse(
            redirect_uri + "?" + urllib.parse.urlencode({"code": code, "state": state}),
            status_code=302,
        )
    except Exception:
        if db.in_transaction:
            db.rollback()
        raise
    finally:
        db.close()


@app.post("/v1/auth/oidc/token")
async def oidc_token(request: Request) -> Response:
    settings = oidc_settings()
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/x-www-form-urlencoded":
        return oidc_token_error("invalid_request")
    try:
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 16 * 1024:
                return oidc_token_error("invalid_request")
        parsed = urllib.parse.parse_qs(raw.decode("ascii"), keep_blank_values=True, strict_parsing=True, max_num_fields=16)
        if any(len(values) != 1 for values in parsed.values()):
            return oidc_token_error("invalid_request")
        fields = {name: values[0] for name, values in parsed.items()}
    except (UnicodeDecodeError, ValueError):
        return oidc_token_error("invalid_request")
    if not oidc_client_auth(request, fields, settings):
        return oidc_token_error("invalid_client", 401)
    auth_scheme = request.headers.get("authorization", "").partition(" ")[0].lower()
    if auth_scheme == "basic" and ("client_id" in fields or "client_secret" in fields):
        return oidc_token_error("invalid_request")
    if fields.get("grant_type") != "authorization_code":
        return oidc_token_error("unsupported_grant_type")
    code = fields.get("code", "")
    redirect_uri = fields.get("redirect_uri", "")
    verifier = fields.get("code_verifier", "")
    if not code or len(code) > 512 or not verifier or not re.fullmatch(r"[A-Za-z0-9._~-]{43,128}", verifier):
        return oidc_token_error("invalid_grant")
    key = oidc_signing_key()
    kid = oidc_key_id(key)
    db = connect()
    try:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT c.*,u.email,m.subject AS oidc_subject FROM oidc_authorization_codes c "
            "JOIN users u ON u.id=c.user_id LEFT JOIN oidc_subject_mappings m ON m.user_id=u.id "
            "WHERE c.code_hash=? AND u.disabled=0",
            (digest_token(code),),
        ).fetchone()
        if (
            not row or row["client_id"] != settings["client_id"] or row["redirect_uri"] != redirect_uri
            or redirect_uri != settings["redirect_uri"] or row["consumed_at"] is not None
            or row["expires_at"] <= utc_now()
        ):
            db.rollback()
            return oidc_token_error("invalid_grant")
        challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
        if not hmac.compare_digest(challenge, row["code_challenge"]):
            db.rollback()
            return oidc_token_error("invalid_grant")

        now = utc_now()
        db.execute("DELETE FROM oidc_access_tokens WHERE expires_at<=? OR revoked_at IS NOT NULL", (now,))
        db.execute(
            "UPDATE oidc_authorization_codes SET consumed_at=? WHERE code_hash=? AND consumed_at IS NULL",
            (now, row["code_hash"]),
        )
        access_token = secrets.token_urlsafe(32)
        expires_at = now + OIDC_ACCESS_TTL
        subject = row["oidc_subject"] or row["user_id"]
        db.execute(
            "INSERT INTO oidc_access_tokens(token_hash,client_id,user_id,subject,scope,created_at,expires_at) VALUES(?,?,?,?,?,?,?)",
            (digest_token(access_token), settings["client_id"], row["user_id"], subject, row["scope"], now, expires_at),
        )
        claims: dict[str, Any] = {
            "iss": settings["issuer"], "sub": subject, "aud": settings["client_id"],
            "iat": now, "exp": expires_at, "email": row["email"], "email_verified": False,
        }
        if "profile" in row["scope"].split():
            claims.update({"name": row["email"], "preferred_username": row["email"]})
        if row["nonce"]:
            claims["nonce"] = row["nonce"]
        id_token = oidc_signed_token(claims, key, kid)
        db.commit()
        return JSONResponse(
            {
                "access_token": access_token, "token_type": "Bearer", "expires_in": OIDC_ACCESS_TTL,
                "id_token": id_token, "scope": row["scope"],
            },
            headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
        )
    except Exception:
        if db.in_transaction:
            db.rollback()
        raise
    finally:
        db.close()


@app.get("/v1/auth/oidc/userinfo")
def oidc_userinfo(request: Request) -> Response:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token or len(token) > 512:
        return JSONResponse(
            {"error": "invalid_token"}, status_code=401,
            headers={"WWW-Authenticate": "Bearer", "Cache-Control": "no-store", "Pragma": "no-cache"},
        )
    db = connect()
    try:
        row = db.execute(
            "SELECT a.scope,a.subject,u.id,u.email,m.subject AS oidc_subject FROM oidc_access_tokens a "
            "JOIN users u ON u.id=a.user_id LEFT JOIN oidc_subject_mappings m ON m.user_id=u.id "
            "WHERE a.token_hash=? AND a.revoked_at IS NULL AND a.expires_at>? AND u.disabled=0",
            (digest_token(token), utc_now()),
        ).fetchone()
        if not row:
            return JSONResponse(
                {"error": "invalid_token"}, status_code=401,
                headers={"WWW-Authenticate": "Bearer", "Cache-Control": "no-store", "Pragma": "no-cache"},
            )
        claims: dict[str, Any] = {"sub": row["subject"] or row["oidc_subject"] or row["id"]}
        scopes = set(row["scope"].split())
        if "email" in scopes:
            claims.update({"email": row["email"], "email_verified": False})
        if "profile" in scopes:
            claims.update({"name": row["email"], "preferred_username": row["email"]})
        return JSONResponse(claims, headers={"Cache-Control": "no-store", "Pragma": "no-cache"})
    finally:
        db.close()


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
def readyz() -> dict[str, str]:
    db = connect()
    try:
        db.execute("SELECT 1").fetchone()
    finally:
        db.close()
    return {"status": "ready"}


@app.post("/v1/auth/bootstrap")
def bootstrap(body: BootstrapInput, request: Request) -> dict[str, Any]:
    verify_origin(request, required=bool(request.headers.get("origin")))
    if not bootstrap_token_matches(body.token):
        raise HTTPException(status_code=403, detail="bootstrap_not_allowed")
    email = normalize_email(body.email)
    db = connect()
    try:
        db.execute("BEGIN IMMEDIATE")
        if is_bootstrap_complete(db):
            raise HTTPException(status_code=409, detail="bootstrap_complete")
        user = db.execute("SELECT * FROM users ORDER BY created_at LIMIT 1").fetchone()
        if user is None:
            now = utc_now()
            user_id = secrets.token_hex(16)
            db.execute(
                "INSERT INTO users(id,email,password_hash,created_at,updated_at) VALUES(?,?,?,?,?)",
                (user_id, email, hash_password(body.password), now, now),
            )
            db.execute("INSERT INTO user_roles(user_id,role) VALUES(?, 'admin')", (user_id,))
            user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            audit(db, user_id, "auth.bootstrap", "created", "web", request_ip(request))
        elif user["email"] != email or not verify_password(user["password_hash"], body.password):
            audit(db, None, "auth.bootstrap", "denied", "web", request_ip(request))
            db.commit()
            raise HTTPException(status_code=403, detail="bootstrap_not_allowed")
        enrollment = issue_totp_enrollment(db, user["id"], email)
        db.commit()
        return {
            "status": "mfa_setup_required",
            "email": email,
            **enrollment,
            "instructions": "Guarda os códigos de recuperação. Confirma um TOTP para concluir o bootstrap do administrador.",
        }
    except Exception:
        if db.in_transaction:
            db.rollback()
        raise
    finally:
        db.close()


@app.post("/v1/auth/bootstrap/verify-mfa")
def verify_bootstrap_mfa(body: BootstrapVerifyInput, request: Request) -> dict[str, str]:
    verify_origin(request, required=bool(request.headers.get("origin")))
    if not bootstrap_token_matches(body.token):
        raise HTTPException(status_code=403, detail="bootstrap_not_allowed")
    email = normalize_email(body.email)
    db = connect()
    try:
        db.execute("BEGIN IMMEDIATE")
        if is_bootstrap_complete(db):
            raise HTTPException(status_code=409, detail="bootstrap_complete")
        user = db.execute("SELECT * FROM users WHERE email=? COLLATE NOCASE", (email,)).fetchone()
        factor = db.execute("SELECT * FROM mfa_factors WHERE user_id=?", (user["id"],)).fetchone() if user else None
        if not user or not factor or not factor["totp_ciphertext"]:
            raise HTTPException(status_code=403, detail="bootstrap_not_allowed")
        try:
            secret = get_fernet().decrypt(factor["totp_ciphertext"].encode()).decode("ascii")
        except (InvalidToken, UnicodeDecodeError) as exc:
            raise HTTPException(status_code=503, detail="mfa_secret_unavailable") from exc
        counter = match_totp(secret, body.code, int(factor["last_counter"]))
        if counter is None:
            audit(db, user["id"], "auth.bootstrap.mfa", "denied", "web", request_ip(request))
            db.commit()
            raise HTTPException(status_code=401, detail="invalid_code")
        now = utc_now()
        db.execute("UPDATE mfa_factors SET enabled=1,last_counter=?,updated_at=? WHERE user_id=?", (counter, now, user["id"]))
        db.execute("INSERT OR REPLACE INTO auth_state(key,value) VALUES('bootstrap_completed','1')")
        audit(db, user["id"], "auth.bootstrap.mfa", "enabled", "web", request_ip(request))
        db.commit()
        return {"status": "bootstrap_complete", "mfa": "enabled"}
    except Exception:
        if db.in_transaction:
            db.rollback()
        raise
    finally:
        db.close()


@app.post("/v1/auth/login")
def login(body: LoginInput, request: Request, response: Response) -> dict[str, Any]:
    if body.client == "web":
        verify_origin(request, required=True)
    email = normalize_email(body.email)
    ip = request_ip(request)
    db = connect()
    try:
        db.execute("BEGIN IMMEDIATE")
        if login_is_limited(db, email, ip):
            raise HTTPException(status_code=429, detail="too_many_attempts")
        user = db.execute("SELECT * FROM users WHERE email=? COLLATE NOCASE", (email,)).fetchone()
        valid_password = verify_password(user["password_hash"] if user else DUMMY_PASSWORD_HASH, body.password)
        if not user or not valid_password or user["disabled"]:
            record_attempt(db, email, ip, False)
            audit(db, user["id"] if user else None, "auth.login", "denied", body.client, ip)
            db.commit()
            raise HTTPException(status_code=401, detail="invalid_credentials")
        roles = [r["role"] for r in db.execute("SELECT role FROM user_roles WHERE user_id=?", (user["id"],)).fetchall()]
        factor = db.execute("SELECT * FROM mfa_factors WHERE user_id=?", (user["id"],)).fetchone()
        if "admin" in roles and (not factor or not factor["enabled"]):
            record_attempt(db, email, ip, False)
            db.commit()
            raise HTTPException(status_code=403, detail="mfa_setup_required")
        if factor and factor["enabled"]:
            if not body.totp_code:
                audit(db, user["id"], "auth.login.mfa", "challenge", body.client, ip)
                db.commit()
                raise HTTPException(status_code=428, detail="mfa_required")
            if not check_totp_or_recovery(db, user["id"], body.totp_code):
                record_attempt(db, email, ip, False)
                audit(db, user["id"], "auth.login.mfa", "denied", body.client, ip)
                db.commit()
                raise HTTPException(status_code=401, detail="invalid_credentials")
        record_attempt(db, email, ip, True)
        if PASSWORD_HASHER.check_needs_rehash(user["password_hash"]):
            db.execute("UPDATE users SET password_hash=?,updated_at=? WHERE id=?", (hash_password(body.password), utc_now(), user["id"]))
        issued = issue_session(db, user, body.client, body.device_name.strip(), ip)
        db.commit()
        cookie_token = issued.pop("_cookie_token", None)
        if cookie_token:
            set_session_cookie(response, cookie_token, WEB_SESSION_TTL)
        return issued
    finally:
        db.close()


@app.post("/v1/auth/firebase/exchange")
def firebase_exchange(body: FirebaseExchangeInput, request: Request, response: Response) -> dict[str, Any]:
    if body.client == "web":
        verify_origin(request, required=True)
    claims = verify_firebase_id_token(body.id_token)
    email = claims["email"]
    firebase_uid = claims["sub"]
    ip = request_ip(request)
    db = connect()
    try:
        db.execute("BEGIN IMMEDIATE")
        if login_is_limited(db, email, ip):
            raise HTTPException(status_code=429, detail="too_many_attempts")

        identity = db.execute(
            "SELECT u.* FROM firebase_identities i JOIN users u ON u.id=i.user_id WHERE i.firebase_uid=?",
            (firebase_uid,),
        ).fetchone()
        user = identity or db.execute("SELECT * FROM users WHERE email=? COLLATE NOCASE", (email,)).fetchone()
        if not user or user["disabled"]:
            record_attempt(db, email, ip, False)
            audit(db, user["id"] if user else None, "auth.firebase.exchange", "denied", body.client, ip)
            db.commit()
            raise HTTPException(status_code=401, detail="invalid_credentials")

        mapped = db.execute("SELECT user_id FROM firebase_identities WHERE firebase_uid=?", (firebase_uid,)).fetchone()
        if mapped and mapped["user_id"] != user["id"]:
            record_attempt(db, email, ip, False)
            audit(db, user["id"], "auth.firebase.exchange", "denied", body.client, ip)
            db.commit()
            raise HTTPException(status_code=401, detail="invalid_credentials")
        if not mapped:
            db.execute(
                "INSERT INTO firebase_identities(firebase_uid,user_id,email,created_at,last_used_at) VALUES(?,?,?,?,?)",
                (firebase_uid, user["id"], email, utc_now(), utc_now()),
            )
        else:
            db.execute("UPDATE firebase_identities SET last_used_at=? WHERE firebase_uid=?", (utc_now(), firebase_uid))

        roles = [row["role"] for row in db.execute("SELECT role FROM user_roles WHERE user_id=?", (user["id"],)).fetchall()]
        factor = db.execute("SELECT enabled FROM mfa_factors WHERE user_id=?", (user["id"],)).fetchone()
        if "admin" in roles and (not factor or not factor["enabled"]):
            db.rollback()
            raise HTTPException(status_code=403, detail="mfa_setup_required")
        if factor and factor["enabled"]:
            if not body.totp_code:
                audit(db, user["id"], "auth.firebase.exchange.mfa", "challenge", body.client, ip)
                db.commit()
                raise HTTPException(status_code=428, detail="mfa_required")
            if not check_totp_or_recovery(db, user["id"], body.totp_code):
                record_attempt(db, email, ip, False)
                audit(db, user["id"], "auth.firebase.exchange.mfa", "denied", body.client, ip)
                db.commit()
                raise HTTPException(status_code=401, detail="invalid_credentials")

        record_attempt(db, email, ip, True)
        device_name = body.device_name.strip() or ("Iku Portal" if body.client == "web" else "Iku Android")
        issued = issue_session(db, user, body.client, device_name, ip)
        audit(db, user["id"], "auth.firebase.exchange", "success", body.client, ip)
        db.commit()
        cookie_token = issued.pop("_cookie_token", None)
        if cookie_token:
            set_session_cookie(response, cookie_token, WEB_SESSION_TTL)
        return issued
    except Exception:
        if db.in_transaction:
            db.rollback()
        raise
    finally:
        db.close()


@app.get("/v1/auth/api-tokens")
def list_api_tokens(request: Request) -> dict[str, Any]:
    db = connect()
    try:
        loaded = load_user_for_token(db, request)
        if not loaded:
            raise HTTPException(status_code=401, detail="not_authenticated")
        current, _, _ = loaded
        require_session_credential(current)
        rows = db.execute(
            "SELECT id,name,token_prefix,scopes_json,created_at,expires_at,last_used_at FROM api_tokens "
            "WHERE user_id=? AND revoked_at IS NULL ORDER BY created_at DESC LIMIT 100",
            (current["user_id"],),
        ).fetchall()
        return {
            "tokens": [
                {
                    "id": row["id"], "name": row["name"], "prefix": row["token_prefix"],
                    "scopes": json.loads(row["scopes_json"]), "created_at": iso_time(row["created_at"]),
                    "expires_at": iso_time(row["expires_at"]) if row["expires_at"] is not None else None,
                    "last_used_at": iso_time(row["last_used_at"]) if row["last_used_at"] else None,
                    "expired": row["expires_at"] is not None and row["expires_at"] <= utc_now(),
                }
                for row in rows
            ]
        }
    finally:
        db.close()


@app.post("/v1/auth/api-tokens")
def create_api_token(body: ApiTokenCreateInput, request: Request) -> dict[str, Any]:
    is_browser_session = not request.headers.get("authorization", "").lower().startswith("bearer ")
    verify_origin(request, required=is_browser_session)
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="invalid_token_name")
    if len(set(body.scopes)) != len(body.scopes) or not set(body.scopes).issubset(API_TOKEN_SCOPES):
        raise HTTPException(status_code=422, detail="invalid_token_scopes")
    db = connect()
    try:
        db.execute("BEGIN IMMEDIATE")
        loaded = load_user_for_token(db, request)
        if not loaded:
            raise HTTPException(status_code=401, detail="not_authenticated")
        current, _, _ = loaded
        require_session_credential(current)
        roles = [row["role"] for row in db.execute("SELECT role FROM user_roles WHERE user_id=?", (current["user_id"],)).fetchall()]
        factor = db.execute("SELECT enabled FROM mfa_factors WHERE user_id=?", (current["user_id"],)).fetchone()
        if "admin" in roles and (not factor or not factor["enabled"]):
            raise HTTPException(status_code=403, detail="mfa_setup_required")
        now = utc_now()
        token = "iku_" + secrets.token_urlsafe(32)
        token_id = secrets.token_hex(16)
        expires_at = now + body.expires_in_days * 24 * 60 * 60
        scopes = sorted(body.scopes)
        db.execute(
            "INSERT INTO api_tokens(id,user_id,name,token_prefix,token_hash,scopes_json,created_at,expires_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (token_id, current["user_id"], name[:80], token[:12], digest_token(token), json.dumps(scopes), now, expires_at),
        )
        audit(db, current["user_id"], "auth.api_token.create", "success", current["client"], request_ip(request))
        db.commit()
        return {
            "token": token,
            "api_token": {
                "id": token_id, "name": name[:80], "prefix": token[:12], "scopes": scopes,
                "created_at": iso_time(now), "expires_at": iso_time(expires_at), "last_used_at": None,
            },
        }
    except Exception:
        if db.in_transaction:
            db.rollback()
        raise
    finally:
        db.close()


@app.post("/v1/auth/api-tokens/revoke")
def revoke_api_token(body: ApiTokenRevokeInput, request: Request) -> dict[str, bool]:
    is_browser_session = not request.headers.get("authorization", "").lower().startswith("bearer ")
    verify_origin(request, required=is_browser_session)
    db = connect()
    try:
        db.execute("BEGIN IMMEDIATE")
        loaded = load_user_for_token(db, request)
        if not loaded:
            raise HTTPException(status_code=401, detail="not_authenticated")
        current, _, _ = loaded
        require_session_credential(current)
        cursor = db.execute(
            "UPDATE api_tokens SET revoked_at=? WHERE id=? AND user_id=? AND revoked_at IS NULL",
            (utc_now(), body.token_id, current["user_id"]),
        )
        if cursor.rowcount != 1:
            raise HTTPException(status_code=404, detail="api_token_not_found")
        audit(db, current["user_id"], "auth.api_token.revoke", "success", current["client"], request_ip(request))
        db.commit()
        return {"revoked": True}
    except Exception:
        if db.in_transaction:
            db.rollback()
        raise
    finally:
        db.close()


@app.get("/v1/auth/session")
def session(request: Request) -> dict[str, Any]:
    db = connect()
    try:
        loaded = load_user_for_token(db, request)
        if not loaded:
            raise HTTPException(status_code=401, detail="not_authenticated")
        session_row, _, _ = loaded
        require_scope(session_row, "profile:read")
        user = db.execute("SELECT id,email FROM users WHERE id=?", (session_row["user_id"],)).fetchone()
        roles = [r["role"] for r in db.execute("SELECT role FROM user_roles WHERE user_id=? ORDER BY role", (user["id"],)).fetchall()]
        factor = db.execute("SELECT enabled FROM mfa_factors WHERE user_id=?", (user["id"],)).fetchone()
        if session_row["credential_type"] == "api_token":
            db.execute("UPDATE api_tokens SET last_used_at=? WHERE id=?", (utc_now(), session_row["id"]))
        else:
            db.execute("UPDATE sessions SET last_seen_at=? WHERE id=?", (utc_now(), session_row["id"]))
        db.commit()
        return {
            "user": {"id": user["id"], "email": user["email"], "roles": roles, "mfa_enabled": bool(factor and factor["enabled"])},
            "session": {
                "id": session_row["id"], "client": session_row["client"],
                "device_name": session_row["device_name"], "created_at": iso_time(session_row["created_at"]),
                "expires_at": iso_time(session_row["expires_at"]),
            },
        }
    finally:
        db.close()


@app.get("/v1/auth/admin/users")
def admin_list_users(request: Request) -> dict[str, Any]:
    db = connect()
    try:
        current = require_admin_session(db, request)
        users = db.execute(
            "SELECT u.id,u.email,u.disabled,u.created_at,u.updated_at,m.enabled AS mfa_enabled "
            "FROM users u LEFT JOIN mfa_factors m ON m.user_id=u.id ORDER BY u.created_at,u.email LIMIT 500"
        ).fetchall()
        roles_by_user: dict[str, list[str]] = {}
        for row in db.execute("SELECT user_id,role FROM user_roles ORDER BY role").fetchall():
            roles_by_user.setdefault(row["user_id"], []).append(row["role"])
        invites = db.execute(
            "SELECT id,email,roles_json,created_at,expires_at FROM user_invites "
            "WHERE accepted_at IS NULL AND revoked_at IS NULL AND expires_at>? ORDER BY created_at DESC LIMIT 100",
            (utc_now(),),
        ).fetchall()
        db.execute("UPDATE sessions SET last_seen_at=? WHERE id=?", (utc_now(), current["id"]))
        db.commit()
        return {
            "users": [
                {
                    "id": row["id"], "email": row["email"], "disabled": bool(row["disabled"]),
                    "roles": roles_by_user.get(row["id"], []), "mfa_enabled": bool(row["mfa_enabled"]),
                    "created_at": iso_time(row["created_at"]), "updated_at": iso_time(row["updated_at"]),
                }
                for row in users
            ],
            "invites": [
                {
                    "id": row["id"], "email": row["email"], "roles": json.loads(row["roles_json"]),
                    "created_at": iso_time(row["created_at"]), "expires_at": iso_time(row["expires_at"]),
                }
                for row in invites
            ],
        }
    finally:
        db.close()


@app.get("/v1/auth/admin/oidc-subjects")
def admin_list_oidc_subjects(request: Request) -> dict[str, Any]:
    db = connect()
    try:
        require_admin_session(db, request)
        rows = db.execute(
            "SELECT user_id,subject,created_at,updated_at FROM oidc_subject_mappings ORDER BY created_at,user_id"
        ).fetchall()
        return {"mappings": [
            {"user_id": row["user_id"], "subject": row["subject"],
             "created_at": iso_time(row["created_at"]), "updated_at": iso_time(row["updated_at"])}
            for row in rows
        ]}
    finally:
        db.close()


@app.post("/v1/auth/admin/oidc-subjects")
def admin_set_oidc_subject(body: AdminOidcSubjectInput, request: Request) -> dict[str, Any]:
    verify_origin(request, required=True)
    db = connect()
    try:
        db.execute("BEGIN IMMEDIATE")
        current = require_admin_session(db, request)
        target = db.execute("SELECT id FROM users WHERE id=? AND disabled=0", (body.user_id,)).fetchone()
        if not target:
            raise HTTPException(status_code=404, detail="user_not_found")
        now = utc_now()
        try:
            db.execute(
                "INSERT INTO oidc_subject_mappings(user_id,subject,created_at,updated_at) VALUES(?,?,?,?) "
                "ON CONFLICT(user_id) DO UPDATE SET subject=excluded.subject,updated_at=excluded.updated_at",
                (body.user_id, body.subject, now, now),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="oidc_subject_in_use") from exc
        audit(db, current["user_id"], "auth.oidc.subject.set", "success", "oidc", request_ip(request))
        db.commit()
        return {"user_id": body.user_id, "subject": body.subject}
    except Exception:
        if db.in_transaction:
            db.rollback()
        raise
    finally:
        db.close()


@app.post("/v1/auth/admin/oidc-subjects/clear")
def admin_clear_oidc_subject(body: AdminOidcSubjectClearInput, request: Request) -> dict[str, Any]:
    verify_origin(request, required=True)
    db = connect()
    try:
        db.execute("BEGIN IMMEDIATE")
        current = require_admin_session(db, request)
        cursor = db.execute("DELETE FROM oidc_subject_mappings WHERE user_id=?", (body.user_id,))
        if cursor.rowcount != 1:
            raise HTTPException(status_code=404, detail="oidc_subject_not_found")
        audit(db, current["user_id"], "auth.oidc.subject.clear", "success", "oidc", request_ip(request))
        db.commit()
        return {"user_id": body.user_id, "cleared": True}
    except Exception:
        if db.in_transaction:
            db.rollback()
        raise
    finally:
        db.close()


@app.post("/v1/auth/admin/invites")
def admin_create_invite(body: AdminInviteCreateInput, request: Request) -> dict[str, Any]:
    verify_origin(request, required=True)
    email = normalize_email(body.email)
    db = connect()
    try:
        db.execute("BEGIN IMMEDIATE")
        current = require_admin_session(db, request)
        if db.execute("SELECT 1 FROM users WHERE email=? COLLATE NOCASE", (email,)).fetchone():
            raise HTTPException(status_code=409, detail="user_already_exists")
        now = utc_now()
        db.execute(
            "UPDATE user_invites SET revoked_at=? WHERE email=? COLLATE NOCASE AND accepted_at IS NULL AND revoked_at IS NULL",
            (now, email),
        )
        invite_id = secrets.token_hex(16)
        token = "iku_inv_" + secrets.token_urlsafe(32)
        expires_at = now + 72 * 60 * 60
        db.execute(
            "INSERT INTO user_invites(id,email,roles_json,token_hash,created_by,created_at,expires_at) VALUES(?,?,?,?,?,?,?)",
            (invite_id, email, json.dumps(["user"]), digest_token(token), current["user_id"], now, expires_at),
        )
        audit(db, current["user_id"], "auth.user_invite.create", "success", current["client"], request_ip(request))
        db.commit()
        return {
            "invitation_token": token,
            "invite": {"id": invite_id, "email": email, "roles": ["user"], "created_at": iso_time(now), "expires_at": iso_time(expires_at)},
        }
    except Exception:
        if db.in_transaction:
            db.rollback()
        raise
    finally:
        db.close()


@app.post("/v1/auth/admin/invites/revoke")
def admin_revoke_invite(body: AdminInviteRevokeInput, request: Request) -> dict[str, bool]:
    verify_origin(request, required=True)
    db = connect()
    try:
        db.execute("BEGIN IMMEDIATE")
        current = require_admin_session(db, request)
        cursor = db.execute(
            "UPDATE user_invites SET revoked_at=? WHERE id=? AND accepted_at IS NULL AND revoked_at IS NULL AND expires_at>?",
            (utc_now(), body.invite_id, utc_now()),
        )
        if cursor.rowcount != 1:
            raise HTTPException(status_code=404, detail="invite_not_found")
        audit(db, current["user_id"], "auth.user_invite.revoke", "success", current["client"], request_ip(request))
        db.commit()
        return {"revoked": True}
    except Exception:
        if db.in_transaction:
            db.rollback()
        raise
    finally:
        db.close()


@app.post("/v1/auth/invites/accept")
def accept_user_invite(body: AdminInviteAcceptInput, request: Request) -> dict[str, Any]:
    verify_origin(request, required=True)
    db = connect()
    try:
        db.execute("BEGIN IMMEDIATE")
        now = utc_now()
        invite = db.execute(
            "SELECT * FROM user_invites WHERE token_hash=? AND accepted_at IS NULL AND revoked_at IS NULL AND expires_at>?",
            (digest_token(body.token), now),
        ).fetchone()
        if not invite:
            raise HTTPException(status_code=400, detail="invite_invalid_or_expired")
        if db.execute("SELECT 1 FROM users WHERE email=? COLLATE NOCASE", (invite["email"],)).fetchone():
            raise HTTPException(status_code=409, detail="user_already_exists")
        roles = json.loads(invite["roles_json"])
        if not roles or not set(roles).issubset({"user"}):
            raise HTTPException(status_code=400, detail="invite_invalid_or_expired")
        user_id = secrets.token_hex(16)
        db.execute(
            "INSERT INTO users(id,email,password_hash,created_at,updated_at) VALUES(?,?,?,?,?)",
            (user_id, invite["email"], hash_password(body.password), now, now),
        )
        db.executemany("INSERT INTO user_roles(user_id,role) VALUES(?,?)", [(user_id, role) for role in roles])
        db.execute("UPDATE user_invites SET accepted_at=? WHERE id=?", (now, invite["id"]))
        audit(db, user_id, "auth.user_invite.accept", "success", "web", request_ip(request))
        db.commit()
        return {"status": "account_created", "email": invite["email"]}
    except Exception:
        if db.in_transaction:
            db.rollback()
        raise
    finally:
        db.close()


@app.post("/v1/auth/admin/users/status")
def admin_set_user_status(body: AdminUserStatusInput, request: Request) -> dict[str, Any]:
    verify_origin(request, required=True)
    db = connect()
    try:
        db.execute("BEGIN IMMEDIATE")
        current = require_admin_session(db, request)
        target = db.execute("SELECT id,email,disabled FROM users WHERE id=?", (body.user_id,)).fetchone()
        if not target:
            raise HTTPException(status_code=404, detail="user_not_found")
        if body.disabled and target["id"] == current["user_id"]:
            raise HTTPException(status_code=409, detail="cannot_disable_current_admin")
        target_roles = {row["role"] for row in db.execute("SELECT role FROM user_roles WHERE user_id=?", (body.user_id,)).fetchall()}
        if body.disabled and "admin" in target_roles:
            active_admins = db.execute(
                "SELECT COUNT(DISTINCT u.id) FROM users u JOIN user_roles r ON r.user_id=u.id "
                "WHERE r.role='admin' AND u.disabled=0"
            ).fetchone()[0]
            if active_admins <= 1:
                raise HTTPException(status_code=409, detail="cannot_disable_last_admin")
        now = utc_now()
        db.execute("UPDATE users SET disabled=?,updated_at=? WHERE id=?", (int(body.disabled), now, body.user_id))
        if body.disabled:
            db.execute("UPDATE sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL", (now, body.user_id))
            db.execute("UPDATE refresh_tokens SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL", (now, body.user_id))
            db.execute("UPDATE api_tokens SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL", (now, body.user_id))
        action = "auth.user.disable" if body.disabled else "auth.user.enable"
        audit(db, current["user_id"], action, "success", current["client"], request_ip(request))
        db.commit()
        return {"user_id": body.user_id, "disabled": body.disabled}
    except Exception:
        if db.in_transaction:
            db.rollback()
        raise
    finally:
        db.close()


@app.get("/v1/auth/sessions")
def list_sessions(request: Request) -> dict[str, Any]:
    db = connect()
    try:
        loaded = load_user_for_token(db, request)
        if not loaded:
            raise HTTPException(status_code=401, detail="not_authenticated")
        current, _, _ = loaded
        require_scope(current, "sessions:read")
        now = utc_now()
        rows = db.execute(
            "SELECT id,client,device_name,created_at,expires_at,last_seen_at FROM sessions "
            "WHERE user_id=? AND revoked_at IS NULL AND expires_at>? "
            "ORDER BY last_seen_at DESC LIMIT 50",
            (current["user_id"], now),
        ).fetchall()
        result = {
            "sessions": [
                {
                    "id": row["id"], "client": row["client"], "device_name": row["device_name"],
                    "created_at": iso_time(row["created_at"]), "expires_at": iso_time(row["expires_at"]),
                    "last_seen_at": iso_time(row["last_seen_at"]), "current": row["id"] == current["id"],
                }
                for row in rows
            ]
        }
        if current["credential_type"] == "api_token":
            db.execute("UPDATE api_tokens SET last_used_at=? WHERE id=?", (utc_now(), current["id"]))
            db.commit()
        return result
    finally:
        db.close()


@app.post("/v1/auth/sessions/revoke")
def revoke_session(body: SessionRevokeInput, request: Request, response: Response) -> dict[str, bool]:
    is_browser_session = not request.headers.get("authorization", "").lower().startswith("bearer ")
    verify_origin(request, required=is_browser_session)
    db = connect()
    try:
        db.execute("BEGIN IMMEDIATE")
        loaded = load_user_for_token(db, request)
        if not loaded:
            raise HTTPException(status_code=401, detail="not_authenticated")
        current, _, _ = loaded
        require_scope(current, "sessions:revoke")
        target = db.execute(
            "SELECT id,user_id,refresh_family,client FROM sessions WHERE id=? AND user_id=? "
            "AND revoked_at IS NULL AND expires_at>?",
            (body.session_id, current["user_id"], utc_now()),
        ).fetchone()
        if not target:
            raise HTTPException(status_code=404, detail="session_not_found")
        now = utc_now()
        if target["refresh_family"]:
            db.execute(
                "UPDATE refresh_tokens SET revoked_at=? WHERE family_id=? AND revoked_at IS NULL",
                (now, target["refresh_family"]),
            )
            db.execute(
                "UPDATE sessions SET revoked_at=? WHERE refresh_family=? AND revoked_at IS NULL",
                (now, target["refresh_family"]),
            )
        else:
            db.execute("UPDATE sessions SET revoked_at=? WHERE id=? AND revoked_at IS NULL", (now, target["id"]))
        audit(db, current["user_id"], "auth.session.revoke", "success", current["client"], request_ip(request))
        db.commit()
        is_current = target["id"] == current["id"]
        if is_current and is_browser_session:
            response.delete_cookie(SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="strict")
        return {"revoked": True, "current": is_current}
    except Exception:
        if db.in_transaction:
            db.rollback()
        raise
    finally:
        db.close()


@app.post("/v1/auth/refresh")
def refresh(body: RefreshInput, request: Request) -> dict[str, Any]:
    ip = request_ip(request)
    db = connect()
    try:
        db.execute("BEGIN IMMEDIATE")
        token_hash = digest_token(body.refresh_token)
        row = db.execute("SELECT * FROM refresh_tokens WHERE token_hash=?", (token_hash,)).fetchone()
        if not row:
            db.commit()
            raise HTTPException(status_code=401, detail="invalid_refresh_token")
        if row["consumed_at"] is not None or row["revoked_at"] is not None:
            db.execute("UPDATE refresh_tokens SET revoked_at=? WHERE family_id=? AND revoked_at IS NULL", (utc_now(), row["family_id"]))
            db.execute("UPDATE sessions SET revoked_at=? WHERE refresh_family=? AND revoked_at IS NULL", (utc_now(), row["family_id"]))
            audit(db, row["user_id"], "auth.refresh.reuse", "revoked_family", "android", ip)
            db.commit()
            raise HTTPException(status_code=401, detail="invalid_refresh_token")
        if row["expires_at"] <= utc_now():
            db.execute("UPDATE refresh_tokens SET revoked_at=? WHERE id=?", (utc_now(), row["id"]))
            db.commit()
            raise HTTPException(status_code=401, detail="invalid_refresh_token")
        db.execute("UPDATE refresh_tokens SET consumed_at=? WHERE id=?", (utc_now(), row["id"]))
        user = db.execute("SELECT * FROM users WHERE id=? AND disabled=0", (row["user_id"],)).fetchone()
        if not user:
            db.execute("UPDATE refresh_tokens SET revoked_at=? WHERE family_id=?", (utc_now(), row["family_id"]))
            db.commit()
            raise HTTPException(status_code=401, detail="invalid_refresh_token")
        issued = issue_session(db, user, "android", body.device_name.strip() or row["device_name"], ip)
        db.execute("UPDATE sessions SET refresh_family=? WHERE id=?", (row["family_id"], issued["session"]["id"]))
        refresh_token = issued["refresh_token"]
        db.execute(
            "UPDATE refresh_tokens SET family_id=? WHERE token_hash=?",
            (row["family_id"], digest_token(refresh_token)),
        )
        db.commit()
        return issued
    finally:
        db.close()


@app.post("/v1/auth/logout", status_code=204)
def logout(request: Request, response: Response, body: LogoutInput | None = None) -> Response:
    is_browser_session = not request.headers.get("authorization", "").lower().startswith("bearer ")
    verify_origin(request, required=is_browser_session)
    db = connect()
    try:
        loaded = load_user_for_token(db, request)
        refresh_row = None
        if body and body.refresh_token:
            refresh_row = db.execute(
                "SELECT user_id,family_id FROM refresh_tokens WHERE token_hash=?",
                (digest_token(body.refresh_token),),
            ).fetchone()
        if loaded:
            session_row, _, _ = loaded
            now = utc_now()
            if refresh_row and session_row["refresh_family"] != refresh_row["family_id"]:
                raise HTTPException(status_code=400, detail="session_token_mismatch")
            if session_row["credential_type"] == "api_token":
                db.execute("UPDATE api_tokens SET revoked_at=? WHERE id=? AND revoked_at IS NULL", (now, session_row["id"]))
            else:
                db.execute("UPDATE sessions SET revoked_at=? WHERE id=?", (now, session_row["id"]))
            family_id = session_row["refresh_family"]
            user_id = session_row["user_id"]
        elif refresh_row:
            now = utc_now()
            family_id = refresh_row["family_id"]
            user_id = refresh_row["user_id"]
        else:
            family_id = None
            user_id = None
        if family_id:
            db.execute("UPDATE refresh_tokens SET revoked_at=? WHERE family_id=? AND revoked_at IS NULL", (now, family_id))
            db.execute("UPDATE sessions SET revoked_at=? WHERE refresh_family=? AND revoked_at IS NULL", (now, family_id))
        if user_id:
            client = "api" if loaded and session_row["credential_type"] == "api_token" else "android" if family_id else "web"
            audit(db, user_id, "auth.logout", "success", client, request_ip(request))
            db.commit()
        response.delete_cookie(SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="strict")
        response.status_code = 204
        return response
    finally:
        db.close()
