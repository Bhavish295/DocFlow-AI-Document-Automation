"""Password hashing and JWT helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
import uuid

import bcrypt
import jwt

from app.core.config import settings


ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(
    *,
    subject: str | uuid.UUID,
    role: str,
    expires_minutes: int | None = None,
) -> str:
    expire_delta = timedelta(
        minutes=expires_minutes
        if expires_minutes is not None
        else settings.AUTH_ACCESS_TOKEN_EXPIRE_MINUTES
    )
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "role": role,
        "iat": now,
        "exp": now + expire_delta,
    }
    return jwt.encode(payload, settings.AUTH_JWT_SECRET, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.AUTH_JWT_SECRET, algorithms=[ALGORITHM])
