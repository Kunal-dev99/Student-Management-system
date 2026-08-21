"""Password hashing and JWT helpers (arch §4, §12.1).

Passwords: pbkdf2_sha256 (strong, pure-Python — avoids native bcrypt version drift on 3.13).
Tokens: short-lived access JWT + longer refresh JWT, HS256 over APP_SECRET_KEY.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

_settings = get_settings()
_pwd = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

ALGORITHM = "HS256"
TokenType = Literal["access", "refresh"]


def hash_password(raw: str) -> str:
    return _pwd.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    return _pwd.verify(raw, hashed)


def generate_opaque_token(nbytes: int = 32) -> str:
    """A high-entropy, URL-safe token (e.g. a password-reset secret)."""
    return secrets.token_urlsafe(nbytes)


def hash_opaque(raw: str) -> str:
    """SHA-256 of a high-entropy token — safe to store, cheap to look up (not for passwords)."""
    return hashlib.sha256(raw.encode()).hexdigest()


def _create_token(subject: str, token_type: TokenType, ttl_seconds: int, extra: dict | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
        "jti": uuid.uuid4().hex,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, _settings.app_secret_key, algorithm=ALGORITHM)


def create_access_token(subject: str, extra: dict | None = None) -> str:
    # Embeds the principal (roles/permissions) so requests resolve without a DB hit — a
    # short-TTL cache of /me role resolution (arch §16). Refresh re-issues with fresh claims.
    return _create_token(subject, "access", _settings.access_token_ttl_seconds, extra)


def create_refresh_token(subject: str) -> str:
    return _create_token(subject, "refresh", _settings.refresh_token_ttl_seconds)


def decode_token(token: str, expected_type: TokenType) -> dict[str, Any]:
    """Returns the claims or raises JWTError (caller maps to AuthError)."""
    claims = jwt.decode(token, _settings.app_secret_key, algorithms=[ALGORITHM])
    if claims.get("type") != expected_type:
        raise JWTError(f"expected {expected_type} token")
    return claims
