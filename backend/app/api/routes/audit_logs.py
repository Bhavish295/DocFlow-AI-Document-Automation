"""Read-only audit log listing (existing AuditLog table)."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.audit_log import AuditLog
from app.models.user import User


router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID | None = None
    action: str
    resource_type: str | None = None
    resource_id: str | None = None
    details: str | None = None
    created_at: datetime


class AuditLogListResponse(BaseModel):
    items: list[AuditLogResponse]
    total: int
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)


@router.get("", response_model=AuditLogListResponse)
def list_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    action: str | None = Query(None),
    resource_type: str | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.USERS_MANAGE)),
) -> AuditLogListResponse:
    filters = []
    if action and action.strip():
        filters.append(AuditLog.action.ilike(f"%{action.strip()}%"))
    if resource_type and resource_type.strip():
        filters.append(AuditLog.resource_type == resource_type.strip())

    count_stmt = select(func.count()).select_from(AuditLog)
    if filters:
        count_stmt = count_stmt.where(*filters)
    total = int(db.scalar(count_stmt) or 0)

    stmt = select(AuditLog).order_by(AuditLog.created_at.desc())
    if filters:
        stmt = stmt.where(*filters)
    rows = list(
        db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    )
    return AuditLogListResponse(
        items=[AuditLogResponse.model_validate(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )
