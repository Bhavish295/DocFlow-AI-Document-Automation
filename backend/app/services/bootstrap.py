"""Bootstrap the first local admin from environment when the users table is empty."""

from __future__ import annotations

from datetime import datetime, timezone
import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.models.user import User, UserRole


logger = logging.getLogger(__name__)


def bootstrap_admin_user(db: Session) -> User | None:
    """Create the first admin only when no users exist and bootstrap env is set."""
    count = db.scalar(select(func.count()).select_from(User)) or 0
    if count > 0:
        return None

    username = (settings.AUTH_BOOTSTRAP_ADMIN_USERNAME or "").strip()
    email = (settings.AUTH_BOOTSTRAP_ADMIN_EMAIL or "").strip().lower()
    password = settings.AUTH_BOOTSTRAP_ADMIN_PASSWORD or ""
    if not username or not email or not password:
        logger.warning(
            "No users exist and bootstrap admin env vars are incomplete; "
            "create an admin via AUTH_BOOTSTRAP_ADMIN_* or the users API after seeding."
        )
        return None

    now = datetime.now(timezone.utc)
    admin = User(
        username=username,
        email=email,
        password_hash=hash_password(password),
        role=UserRole.ADMIN.value,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    logger.info("Bootstrap admin user created: %s", admin.username)
    return admin
