from fastapi import APIRouter, Depends, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser
from app.core.database import get_db
from app.core.rate_limit import enforce_login_rate_limit
from app.schemas.user import LoginRequest, TokenResponse, UserResponse
from app.services.auth_service import AuthService


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login_json(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    enforce_login_rate_limit(request)
    return AuthService(db).login(payload)


@router.post("/token", response_model=TokenResponse, include_in_schema=True)
def login_form(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> TokenResponse:
    """OAuth2 password-flow compatible login (form username/password)."""
    enforce_login_rate_limit(request)
    return AuthService(db).login(
        LoginRequest(username=form_data.username, password=form_data.password)
    )


@router.get("/me", response_model=UserResponse)
def read_me(current_user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(current_user)
