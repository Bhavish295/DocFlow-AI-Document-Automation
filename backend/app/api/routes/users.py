import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import AdminUser
from app.core.database import get_db
from app.schemas.user import UserCreate, UserListResponse, UserResponse, UserUpdate
from app.services.user_service import UserService


router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    admin: AdminUser,
    db: Session = Depends(get_db),
) -> UserResponse:
    return UserService(db).create_user(payload, actor_id=admin.id)


@router.get("", response_model=UserListResponse)
def list_users(
    admin: AdminUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> UserListResponse:
    return UserService(db).list_users(page=page, page_size=page_size)


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: uuid.UUID,
    admin: AdminUser,
    db: Session = Depends(get_db),
) -> UserResponse:
    return UserService(db).to_response(UserService(db).get_user(user_id))


@router.patch("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    admin: AdminUser,
    db: Session = Depends(get_db),
) -> UserResponse:
    return UserService(db).update_user(user_id, payload, actor_id=admin.id)


@router.delete("/{user_id}", response_model=UserResponse)
def deactivate_user(
    user_id: uuid.UUID,
    admin: AdminUser,
    db: Session = Depends(get_db),
) -> UserResponse:
    return UserService(db).deactivate_user(user_id, actor_id=admin.id)
