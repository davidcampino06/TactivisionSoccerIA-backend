"""Password hashing (bcrypt) and JWT tokens."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from config import settings

ACCESS_TOKEN_PURPOSE = "access"
PASSWORD_RESET_PURPOSE = "password_reset"


class InvalidTokenError(ValueError):
    pass


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def _encode(payload: dict, minutes: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {**payload, "iat": now, "exp": now + timedelta(minutes=minutes)}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def _decode(token: str, purpose: str) -> dict:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as error:
        raise InvalidTokenError("Invalid or expired token.") from error
    if payload.get("purpose") != purpose:
        raise InvalidTokenError("Token purpose mismatch.")
    return payload


def create_access_token(user_id: str, role: str) -> str:
    return _encode({"sub": user_id, "role": role, "purpose": ACCESS_TOKEN_PURPOSE},
                   settings.access_token_expire_minutes)


def decode_access_token(token: str) -> dict:
    return _decode(token, ACCESS_TOKEN_PURPOSE)


def password_fingerprint(password_hash: str) -> str:
    """Changes when the password changes, so a reset token can be used only once."""
    return hashlib.sha256(password_hash.encode("utf-8")).hexdigest()[:16]


def create_password_reset_token(user_id: str, password_hash: str) -> str:
    return _encode(
        {"sub": user_id, "purpose": PASSWORD_RESET_PURPOSE, "fp": password_fingerprint(password_hash)},
        settings.password_reset_expire_minutes,
    )


def decode_password_reset_token(token: str) -> dict:
    return _decode(token, PASSWORD_RESET_PURPOSE)
