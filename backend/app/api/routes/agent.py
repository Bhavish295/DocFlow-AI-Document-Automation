"""Controlled agent API routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.database import get_db
from app.core.permissions import Permission
from app.core.rate_limit import enforce_ai_rate_limit
from app.models.user import User
from app.schemas.agent import AgentAskRequest, AgentAskResponse, AgentRunListResponse
from app.services.agent.agent_orchestrator import AgentOrchestrator


router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/ask", response_model=AgentAskResponse)
def agent_ask(
    payload: AgentAskRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.AGENT_USE)),
) -> AgentAskResponse:
    enforce_ai_rate_limit(request)
    return AgentOrchestrator(db).ask(payload, user=user)


@router.get("/runs", response_model=AgentRunListResponse)
def list_agent_runs(
    conversation_id: uuid.UUID | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.AGENT_USE)),
) -> AgentRunListResponse:
    return AgentOrchestrator(db).list_runs(
        user=user,
        conversation_id=conversation_id,
        page=page,
        page_size=page_size,
    )
