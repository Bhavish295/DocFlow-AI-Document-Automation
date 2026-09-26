from datetime import datetime
from typing import Any
import uuid

from pydantic import BaseModel, Field


class WorkflowResponse(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    description: str
    trigger_type: str
    status: str
    allowed_actions: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class WorkflowStepExecutionResponse(BaseModel):
    id: uuid.UUID
    step_name: str
    step_type: str
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    result: dict[str, Any] | None = None
    error_message: str | None = None


class WorkflowExecutionResponse(BaseModel):
    id: uuid.UUID
    workflow_id: uuid.UUID
    workflow_code: str | None = None
    workflow_name: str | None = None
    trigger_event: str
    entity_type: str
    entity_id: str
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    error_message: str | None = None
    execution_metadata: dict[str, Any] | None = None
    allowed_actions: list[str] = Field(default_factory=list)
    steps: list[WorkflowStepExecutionResponse] = Field(default_factory=list)
    reason: str | None = None


class WorkflowTriggerRequest(BaseModel):
    entity_type: str = Field(..., min_length=1, max_length=100)
    entity_id: str = Field(..., min_length=1, max_length=100)
    trigger_event: str | None = None
    force: bool = False
    metadata: dict[str, Any] | None = None


class WorkflowExecutionListResponse(BaseModel):
    workflow_id: uuid.UUID
    items: list[WorkflowExecutionResponse]
    total: int
    page: int
    page_size: int


class WorkflowListResponse(BaseModel):
    items: list[WorkflowResponse]
