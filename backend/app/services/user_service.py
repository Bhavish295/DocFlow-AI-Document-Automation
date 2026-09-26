"""User management service (admin)."""

from __future__ import annotations

from datetime import datetime, timezone
import re
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.password_policy import validate_password_strength
from app.core.security import hash_password
from app.models.user import User, UserRole
from app.schemas.user import UserCreate, UserListResponse, UserResponse, UserUpdate
from app.services.audit_service import AuditService


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
VALID_ROLES = {role.value for role in UserRole}


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _validate_email(email: str) -> str:
    normalized = _normalize_email(email)
    if not EMAIL_RE.match(normalized):
        raise AppError("Invalid email address.", status_code=400)
    return normalized


def _validate_role(role: str) -> str:
    value = (role or "").strip().lower()
    if value not in VALID_ROLES:
        raise AppError(
            f"Invalid role. Allowed: {', '.join(sorted(VALID_ROLES))}.",
            status_code=400,
        )
    return value


class UserService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)

    def to_response(self, user: User) -> UserResponse:
        return UserResponse.model_validate(user)

    def get_user(self, user_id: uuid.UUID) -> User:
        user = self.db.get(User, user_id)
        if user is None:
            raise AppError("User not found.", status_code=404)
        return user

    def list_users(self, *, page: int = 1, page_size: int = 20) -> UserListResponse:
        page = max(1, page)
        page_size = min(100, max(1, page_size))
        total = self.db.scalar(select(func.count()).select_from(User)) or 0
        rows = list(
            self.db.scalars(
                select(User)
                .order_by(User.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        return UserListResponse(
            items=[self.to_response(row) for row in rows],
            total=int(total),
            page=page,
            page_size=page_size,
        )

    def create_user(self, payload: UserCreate, *, actor_id: uuid.UUID | None = None) -> UserResponse:
        username = payload.username.strip()
        email = _validate_email(payload.email)
        role = _validate_role(payload.role)
        validate_password_strength(payload.password)
        self._ensure_unique(username=username, email=email)

        now = datetime.now(timezone.utc)
        user = User(
            username=username,
            email=email,
            password_hash=hash_password(payload.password),
            role=role,
            is_active=payload.is_active,
            created_at=now,
            updated_at=now,
        )
        self.db.add(user)
        self.db.flush()
        self.audit.log(
            action="user_created",
            user_id=actor_id,
            resource_type="user",
            resource_id=user.id,
            details={"username": user.username, "role": user.role},
            commit=False,
        )
        self.db.commit()
        self.db.refresh(user)
        return self.to_response(user)

    def update_user(
        self,
        user_id: uuid.UUID,
        payload: UserUpdate,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> UserResponse:
        user = self.get_user(user_id)
        data = payload.model_dump(exclude_unset=True)

        if "username" in data and data["username"] is not None:
            username = data["username"].strip()
            self._ensure_unique(username=username, email=None, exclude_id=user.id)
            user.username = username
        if "email" in data and data["email"] is not None:
            email = _validate_email(data["email"])
            self._ensure_unique(username=None, email=email, exclude_id=user.id)
            user.email = email
        if "role" in data and data["role"] is not None:
            new_role = _validate_role(data["role"])
            if user.role == UserRole.ADMIN.value and new_role != UserRole.ADMIN.value:
                self._ensure_not_last_active_admin(user.id)
            user.role = new_role
        if "password" in data and data["password"]:
            validate_password_strength(data["password"])
            user.password_hash = hash_password(data["password"])
        if "is_active" in data and data["is_active"] is not None:
            if user.is_active and data["is_active"] is False:
                if user.role == UserRole.ADMIN.value:
                    self._ensure_not_last_active_admin(user.id)
                self.audit.log(
                    action="user_deactivated",
                    user_id=actor_id,
                    resource_type="user",
                    resource_id=user.id,
                    details={"username": user.username},
                    commit=False,
                )
            user.is_active = bool(data["is_active"])

        user.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(user)
        return self.to_response(user)

    def deactivate_user(
        self,
        user_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> UserResponse:
        return self.update_user(
            user_id,
            UserUpdate(is_active=False),
            actor_id=actor_id,
        )

    def _ensure_unique(
        self,
        *,
        username: str | None,
        email: str | None,
        exclude_id: uuid.UUID | None = None,
    ) -> None:
        if username:
            query = select(User).where(func.lower(User.username) == username.lower())
            if exclude_id:
                query = query.where(User.id != exclude_id)
            if self.db.scalar(query):
                raise AppError("Username is already in use.", status_code=409)
        if email:
            query = select(User).where(func.lower(User.email) == email.lower())
            if exclude_id:
                query = query.where(User.id != exclude_id)
            if self.db.scalar(query):
                raise AppError("Email is already in use.", status_code=409)

    def _ensure_not_last_active_admin(self, user_id: uuid.UUID) -> None:
        active_admins = list(
            self.db.scalars(
                select(User).where(
                    User.role == UserRole.ADMIN.value,
                    User.is_active.is_(True),
                )
            ).all()
        )
        if len(active_admins) <= 1 and any(admin.id == user_id for admin in active_admins):
            raise AppError(
                "Cannot remove or demote the last active admin account.",
                status_code=400,
            )

    def find_by_username_or_email(self, identifier: str) -> User | None:
        value = identifier.strip()
        return self.db.scalar(
            select(User).where(
                or_(
                    func.lower(User.username) == value.lower(),
                    func.lower(User.email) == value.lower(),
                )
            )
        )
