"""Password strength rules for newly created / updated users (not bootstrap)."""

from __future__ import annotations

import re

from app.core.config import settings
from app.core.exceptions import AppError


def validate_password_strength(password: str) -> None:
    """Raise AppError when password does not meet configured strength rules."""
    value = password or ""
    min_len = settings.AUTH_PASSWORD_MIN_LENGTH
    if len(value) < min_len:
        raise AppError(
            f"Password must be at least {min_len} characters.",
            status_code=400,
        )
    if len(value) > 200:
        raise AppError("Password is too long.", status_code=400)
    if settings.AUTH_PASSWORD_REQUIRE_LETTER and not re.search(r"[A-Za-z]", value):
        raise AppError("Password must include at least one letter.", status_code=400)
    if settings.AUTH_PASSWORD_REQUIRE_DIGIT and not re.search(r"\d", value):
        raise AppError("Password must include at least one digit.", status_code=400)
    if settings.AUTH_PASSWORD_REQUIRE_SPECIAL and not re.search(
        r"[^A-Za-z0-9]", value
    ):
        raise AppError(
            "Password must include at least one special character.",
            status_code=400,
        )
