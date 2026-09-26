from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.database import get_db
from app.core.permissions import Permission
from app.core.rate_limit import enforce_ai_rate_limit
from app.models.user import User
from app.schemas.rag import RagAskRequest, RagAskResponse, RagSearchRequest, RagSearchResponse
from app.services.rag_answer import RagAnswerService


router = APIRouter(prefix="/rag")


@router.post("/search", response_model=RagSearchResponse)
def rag_search(
    payload: RagSearchRequest,
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.RAG_USE)),
) -> RagSearchResponse:
    enforce_ai_rate_limit(request)
    return RagAnswerService(db).search(
        payload.query,
        top_k=payload.top_k,
        document_id=payload.document_id,
        document_type=payload.document_type,
    )


@router.post("/ask", response_model=RagAskResponse)
def rag_ask(
    payload: RagAskRequest,
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.RAG_USE)),
) -> RagAskResponse:
    enforce_ai_rate_limit(request)
    return RagAnswerService(db).ask(
        payload.question,
        top_k=payload.top_k,
        document_id=payload.document_id,
        document_type=payload.document_type,
    )
