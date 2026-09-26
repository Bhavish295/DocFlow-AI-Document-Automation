from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.user import User
from app.schemas.workflow import (
    WorkflowExecutionListResponse,
    WorkflowExecutionResponse,
    WorkflowListResponse,
    WorkflowResponse,
    WorkflowTriggerRequest,
)
from app.services.audit_service import AuditService
from app.services.workflow_definitions import get_definition_by_code
from app.services.workflow_engine import WorkflowEngine


router = APIRouter()


def _to_workflow_response(workflow) -> WorkflowResponse:
    definition = get_definition_by_code(workflow.code) or {}
    return WorkflowResponse(
        id=workflow.id,
        code=workflow.code,
        name=workflow.name,
        description=workflow.description,
        trigger_type=workflow.trigger_type,
        status=workflow.status,
        allowed_actions=[action["type"] for action in definition.get("actions") or []],
        created_at=workflow.created_at,
        updated_at=workflow.updated_at,
    )


@router.get("/workflows", response_model=WorkflowListResponse)
def list_workflows(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.WORKFLOWS_READ)),
) -> WorkflowListResponse:
    workflows = WorkflowEngine(db).list_workflows()
    return WorkflowListResponse(items=[_to_workflow_response(item) for item in workflows])


@router.get("/workflows/{workflow_id}", response_model=WorkflowResponse)
def get_workflow(
    workflow_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.WORKFLOWS_READ)),
) -> WorkflowResponse:
    workflow = WorkflowEngine(db).get_workflow(workflow_id)
    return _to_workflow_response(workflow)


@router.post("/workflows/{workflow_id}/trigger", response_model=WorkflowExecutionResponse)
def trigger_workflow(
    workflow_id: UUID,
    payload: WorkflowTriggerRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.WORKFLOWS_TRIGGER)),
) -> WorkflowExecutionResponse:
    AuditService(db).log(
        action="workflow_triggered",
        user_id=user.id,
        resource_type="workflow",
        resource_id=workflow_id,
        details={"trigger_event": payload.trigger_event},
    )
    result = WorkflowEngine(db).trigger_workflow(
        workflow_id,
        trigger_event=payload.trigger_event,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        metadata=payload.metadata,
        force=payload.force,
    )
    return WorkflowExecutionResponse(**result)


@router.get("/workflows/{workflow_id}/executions", response_model=WorkflowExecutionListResponse)
def list_workflow_executions(
    workflow_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.WORKFLOWS_READ)),
) -> WorkflowExecutionListResponse:
    payload = WorkflowEngine(db).list_executions(workflow_id, page=page, page_size=page_size)
    return WorkflowExecutionListResponse(**payload)


@router.get("/workflow-executions/{execution_id}", response_model=WorkflowExecutionResponse)
def get_workflow_execution(
    execution_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.WORKFLOWS_READ)),
) -> WorkflowExecutionResponse:
    payload = WorkflowEngine(db).get_execution(execution_id)
    return WorkflowExecutionResponse(**payload)
