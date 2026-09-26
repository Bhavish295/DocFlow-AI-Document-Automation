from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.database import get_db
from app.core.permissions import Permission
from app.core.rate_limit import enforce_ai_rate_limit
from app.models.user import User
from app.schemas.sql_agent import (
    SqlAskRequest,
    SqlAskResponse,
    SqlValidateRequest,
    SqlValidateResponse,
)
from app.services.sql_agent import SqlAgentService, validate_sql_only


router = APIRouter(prefix="/sql")


@router.post("/ask", response_model=SqlAskResponse)
def sql_ask(
    payload: SqlAskRequest,
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.SQL_USE)),
) -> SqlAskResponse:
    enforce_ai_rate_limit(request)
    result = SqlAgentService(db).ask(payload.question, max_rows=payload.max_rows)
    return SqlAskResponse(**result)


@router.post("/validate", response_model=SqlValidateResponse)
def sql_validate(
    payload: SqlValidateRequest,
    _: User = Depends(require_permission(Permission.SQL_USE)),
) -> SqlValidateResponse:
    result = validate_sql_only(payload.sql)
    return SqlValidateResponse(**result)
