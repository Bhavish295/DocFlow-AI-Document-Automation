"""Authentication service (login / token)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.login_protection import login_failure_tracker
from app.core.security import create_access_token, verify_password
from app.schemas.user import LoginRequest, TokenResponse, UserResponse
from app.services.audit_service import AuditService
from app.services.user_service import UserService


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = UserService(db)
        self.audit = AuditService(db)

    def login(self, payload: LoginRequest) -> TokenResponse:
        identifier = (payload.username or "").strip()
        login_failure_tracker.assert_not_locked(identifier)

        user = self.users.find_by_username_or_email(identifier)
        if user is None or not verify_password(payload.password, user.password_hash):
            login_failure_tracker.record_failure(identifier)
            self.audit.log(
                action="login_failed",
                user_id=None,
                resource_type="auth",
                details={"username": identifier[:100]},
            )
            # Same message whether user missing or password wrong
            raise AppError("Invalid username/email or password.", status_code=401)

        if not user.is_active:
            login_failure_tracker.record_failure(identifier)
            self.audit.log(
                action="login_failed",
                user_id=user.id,
                resource_type="auth",
                details={"reason": "inactive"},
            )
            raise AppError("Invalid username/email or password.", status_code=401)

        login_failure_tracker.clear(identifier)
        token = create_access_token(subject=user.id, role=user.role)
        self.audit.log(
            action="login_success",
            user_id=user.id,
            resource_type="auth",
            resource_id=user.id,
        )
        return TokenResponse(
            access_token=token,
            token_type="bearer",
            user=UserResponse.model_validate(user),
        )
