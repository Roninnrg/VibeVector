"""Локальные аккаунты и сессии «Вектора» без внешних OAuth-сервисов."""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse

from . import db

COOKIE_NAME = "vector_session"
SESSION_DAYS = 30
PASSWORD_ITERATIONS = 210_000
AVATARS = ("lime", "sky", "violet", "amber", "coral", "mint")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def normalize_email(value: str) -> str:
    return str(value or "").strip().lower()


def valid_email(value: str) -> bool:
    return bool(EMAIL_RE.match(value)) and len(value) <= 200


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            _unb64(salt),
            int(iterations),
        )
        return hmac.compare_digest(_b64(digest), expected)
    except (TypeError, ValueError):
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(conn: sqlite3.Connection, user_id: str, request: Request) -> str:
    token = secrets.token_urlsafe(32)
    created = now_utc()
    expires = created + timedelta(days=SESSION_DAYS)
    conn.execute(
        "INSERT INTO sessions(token_hash, user_id, user_agent, created_at, expires_at) "
        "VALUES(?,?,?,?,?)",
        (
            token_hash(token),
            user_id,
            (request.headers.get("user-agent") or "")[:300],
            created.isoformat(timespec="seconds"),
            expires.isoformat(timespec="seconds"),
        ),
    )
    conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (created.isoformat(timespec="seconds"),))
    return token


def session_token(request: Request) -> str:
    token = request.cookies.get(COOKIE_NAME, "").strip()
    return token if 16 <= len(token) <= 200 else ""


def current_user(request: Request) -> dict[str, Any] | None:
    token = session_token(request)
    if not token:
        return None
    with db.db() as conn:
        row = conn.execute(
            """SELECT u.* FROM sessions s
               JOIN users u ON u.id = s.user_id
               WHERE s.token_hash = ? AND s.expires_at > ?""",
            (token_hash(token), now_utc().isoformat(timespec="seconds")),
        ).fetchone()
    return public_user(row) if row else None


def require_user(request: Request) -> dict[str, Any]:
    user = current_user(request)
    if not user:
        raise HTTPException(401, "Войдите в аккаунт, чтобы продолжить.")
    return user


def public_user(row: sqlite3.Row | dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    item = dict(row)
    item.pop("password_hash", None)
    item["avatar"] = item.get("avatar") if item.get("avatar") in AVATARS else "lime"
    return item


def is_secure_request(request: Request) -> bool:
    proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    return request.url.scheme == "https" or proto == "https"


def set_session_cookie(response: Response, token: str, request: Request) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=SESSION_DAYS * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=is_secure_request(request),
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, samesite="lax")


def revoke_session(request: Request) -> None:
    token = session_token(request)
    if not token:
        return
    with db.db() as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash(token),))


def revoke_other_sessions(request: Request, user_id: str) -> None:
    token = session_token(request)
    with db.db() as conn:
        if token:
            conn.execute(
                "DELETE FROM sessions WHERE user_id = ? AND token_hash != ?",
                (user_id, token_hash(token)),
            )
        else:
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))


def auth_error(message: str = "Войдите в аккаунт, чтобы продолжить.") -> JSONResponse:
    return JSONResponse(status_code=401, content={"detail": message})
