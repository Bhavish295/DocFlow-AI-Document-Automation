from typing import Any

from pydantic import BaseModel, Field


class InvestigationRequest(BaseModel):
    question: str = Field(..., min_length=1)


class InvestigationStep(BaseModel):
    question: str
    sql: str | None = None
    row_count: int = 0
    status: str | None = None


class InvestigationEvidence(BaseModel):
    description: str
    data: list[dict[str, Any]] = Field(default_factory=list)
    step_id: str | None = None


class InvestigationFinding(BaseModel):
    title: str
    description: str
    type: str


class InvestigationResponse(BaseModel):
    question: str
    status: str
    summary: str | None = None
    findings: list[InvestigationFinding] = Field(default_factory=list)
    evidence: list[InvestigationEvidence] = Field(default_factory=list)
    queries: list[InvestigationStep] = Field(default_factory=list)
    suggested_next_steps: list[str] = Field(default_factory=list)
