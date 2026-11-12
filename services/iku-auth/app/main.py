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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import urlopen
from urllib.parse import quote

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse

DB_PATH = Path(os.getenv("IKU_AUTH_DB_PATH", "/var/lib/iku-auth/auth.sqlite3"))
SESSION_COOKIE = "iku_session"
WEB_SESSION_TTL = 8 * 60 * 60
ACCESS_TOKEN_TTL = 15 * 60
REFRESH_TOKEN_TTL = 30 * 24 * 60 * 60
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


class FirebaseExchangeInput(StrictModel):
    id_token: str = Field(min_length=100, max_length=8192)
    totp_code: str | None = Field(default=None, min_length=6, max_length=16)
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
                token_hash TEXT NOT NULL UNIQUE,
                scopes_json TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                expires_at INTEGER,
                last_used_at INTEGER,
                revoked_at INTEGER
            );
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
            INSERT OR IGNORE INTO roles(name) VALUES ('admin'), ('server'), ('user'), ('api');
            PRAGMA user_version=1;
            """
        )
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
        "SELECT s.*,u.email,u.disabled FROM sessions s JOIN users u ON u.id=s.user_id "
        "WHERE s.token_hash=? AND s.revoked_at IS NULL AND s.expires_at>?",
        (digest_token(token), now),
    ).fetchone()
    if not row or row["disabled"]:
        return None
    roles = db.execute("SELECT role FROM user_roles WHERE user_id=? ORDER BY role", (row["user_id"],)).fetchall()
    return row, row, token


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
def firebase_exchange(body: FirebaseExchangeInput, request: Request) -> dict[str, Any]:
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
            audit(db, user["id"] if user else None, "auth.firebase.exchange", "denied", "android", ip)
            db.commit()
            raise HTTPException(status_code=401, detail="invalid_credentials")

        mapped = db.execute("SELECT user_id FROM firebase_identities WHERE firebase_uid=?", (firebase_uid,)).fetchone()
        if mapped and mapped["user_id"] != user["id"]:
            record_attempt(db, email, ip, False)
            audit(db, user["id"], "auth.firebase.exchange", "denied", "android", ip)
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
                audit(db, user["id"], "auth.firebase.exchange.mfa", "challenge", "android", ip)
                db.commit()
                raise HTTPException(status_code=428, detail="mfa_required")
            if not check_totp_or_recovery(db, user["id"], body.totp_code):
                record_attempt(db, email, ip, False)
                audit(db, user["id"], "auth.firebase.exchange.mfa", "denied", "android", ip)
                db.commit()
                raise HTTPException(status_code=401, detail="invalid_credentials")

        record_attempt(db, email, ip, True)
        issued = issue_session(db, user, "android", body.device_name.strip() or "Iku Android", ip)
        audit(db, user["id"], "auth.firebase.exchange", "success", "android", ip)
        db.commit()
        return issued
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
        user = db.execute("SELECT id,email FROM users WHERE id=?", (session_row["user_id"],)).fetchone()
        roles = [r["role"] for r in db.execute("SELECT role FROM user_roles WHERE user_id=? ORDER BY role", (user["id"],)).fetchall()]
        factor = db.execute("SELECT enabled FROM mfa_factors WHERE user_id=?", (user["id"],)).fetchone()
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


@app.get("/v1/auth/sessions")
def list_sessions(request: Request) -> dict[str, Any]:
    db = connect()
    try:
        loaded = load_user_for_token(db, request)
        if not loaded:
            raise HTTPException(status_code=401, detail="not_authenticated")
        current, _, _ = loaded
        now = utc_now()
        rows = db.execute(
            "SELECT id,client,device_name,created_at,expires_at,last_seen_at FROM sessions "
            "WHERE user_id=? AND revoked_at IS NULL AND expires_at>? "
            "ORDER BY last_seen_at DESC LIMIT 50",
            (current["user_id"], now),
        ).fetchall()
        return {
            "sessions": [
                {
                    "id": row["id"], "client": row["client"], "device_name": row["device_name"],
                    "created_at": iso_time(row["created_at"]), "expires_at": iso_time(row["expires_at"]),
                    "last_seen_at": iso_time(row["last_seen_at"]), "current": row["id"] == current["id"],
                }
                for row in rows
            ]
        }
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
            audit(db, user_id, "auth.logout", "success", "android" if family_id else "web", request_ip(request))
            db.commit()
        response.delete_cookie(SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="strict")
        response.status_code = 204
        return response
    finally:
        db.close()
