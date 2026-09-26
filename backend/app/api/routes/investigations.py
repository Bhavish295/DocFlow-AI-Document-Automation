from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.database import get_db
from app.core.permissions import Permission
from app.core.rate_limit import enforce_ai_rate_limit
from app.models.user import User
from app.schemas.investigation import InvestigationRequest, InvestigationResponse
from app.services.investigation_agent import InvestigationAgent


router = APIRouter(prefix="/investigations")


@router.post("/ask", response_model=InvestigationResponse)
def investigate_ask(
    payload: InvestigationRequest,
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.INVESTIGATION_USE)),
) -> InvestigationResponse:
    enforce_ai_rate_limit(request)
    result = InvestigationAgent(db).investigate(payload.question)
    return InvestigationResponse(**result)
