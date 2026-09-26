from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AgentAskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    conversation_id: uuid.UUID | None = None
    max_steps: int | None = Field(default=None, ge=1, le=10)


class AgentStepResult(BaseModel):
    step_number: int
    tool_name: str
    purpose: str
    status: str
    concise_result_summary: str


class AgentEvidenceItem(BaseModel):
    source: str
    summary: str
    details: dict[str, Any] | None = None


class AgentAskResponse(BaseModel):
    answer: str
    status: str
    steps: list[AgentStepResult] = Field(default_factory=list)
    evidence: list[AgentEvidenceItem] = Field(default_factory=list)
    tools_used: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    conversation_id: uuid.UUID
    run_id: uuid.UUID | None = None


class AgentRunSummary(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    question: str
    status: str
    answer: str
    tools_used: list[str] = Field(default_factory=list)
    step_count: int = 0
    created_at: datetime


class AgentRunListResponse(BaseModel):
    items: list[AgentRunSummary]
    total: int
    page: int
    page_size: int
