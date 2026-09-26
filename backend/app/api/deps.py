"""FastAPI auth/RBAC dependencies."""

from __future__ import annotations

from typing import Annotated, Callable
import uuid

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from jwt import InvalidTokenError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import AppError
from app.core.permissions import Permission, role_has_permission
from app.core.security import decode_access_token
from app.models.user import User, UserRole


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)


def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    if not token:
        raise AppError("Not authenticated.", status_code=401)
    try:
        payload = decode_access_token(token)
        subject = payload.get("sub")
        if not subject:
            raise AppError("Invalid authentication token.", status_code=401)
        user_id = uuid.UUID(str(subject))
    except (InvalidTokenError, ValueError, TypeError):
        raise AppError("Invalid or expired authentication token.", status_code=401) from None

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise AppError("User is inactive or not found.", status_code=401)
    return user


def require_authenticated_user(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    return user


def require_permission(permission: Permission) -> Callable[..., User]:
    def dependency(user: Annotated[User, Depends(get_current_user)]) -> User:
        if not role_has_permission(user.role, permission):
            raise AppError("Insufficient permissions for this action.", status_code=403)
        return user

    return dependency


def require_roles(*roles: str) -> Callable[..., User]:
    allowed = {role.lower() for role in roles}

    def dependency(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role == UserRole.ADMIN.value:
            return user
        if user.role not in allowed:
            raise AppError("Insufficient permissions for this action.", status_code=403)
        return user

    return dependency


def require_admin(user: Annotated[User, Depends(require_permission(Permission.USERS_MANAGE))]) -> User:
    return user


def require_reviewer(
    user: Annotated[User, Depends(require_permission(Permission.REVIEWS_WRITE))],
) -> User:
    return user


def require_operator(
    user: Annotated[User, Depends(require_permission(Permission.DOCUMENTS_PROCESS))],
) -> User:
    return user


def require_viewer(
    user: Annotated[User, Depends(require_permission(Permission.DOCUMENTS_READ))],
) -> User:
    return user


# Convenience aliases used by routes
CurrentUser = Annotated[User, Depends(require_authenticated_user)]
ViewerUser = Annotated[User, Depends(require_viewer)]
OperatorUser = Annotated[User, Depends(require_operator)]
ReviewerUser = Annotated[User, Depends(require_reviewer)]
AdminUser = Annotated[User, Depends(require_admin)]
