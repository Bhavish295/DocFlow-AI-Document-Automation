"""Controlled workflow execution engine (allowlisted actions only)."""

from __future__ import annotations

from contextvars import ContextVar
from datetime import datetime, timezone
import logging
from typing import Any
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppError
from app.models.document_review import ReviewPriority, ReviewReason
from app.models.workflow import (
    Workflow,
    WorkflowExecution,
    WorkflowExecutionStatus,
    WorkflowStatus,
    WorkflowStepExecution,
    WorkflowStepStatus,
)
from app.services.workflow_conditions import WorkflowContext, build_context, evaluate_conditions
from app.services.workflow_definitions import (
    ALLOWED_ACTION_TYPES,
    ALLOWED_TRIGGER_TYPES,
    PREDEFINED_WORKFLOWS,
    get_definition_by_code,
    validate_definition,
)
from app.services.document_review import DocumentReviewService
from app.services.validation_service import ValidationService
from app.schemas.validation import ValidationResponse

logger = logging.getLogger(__name__)

_workflow_depth: ContextVar[int] = ContextVar("workflow_depth", default=0)
_workflow_stack: ContextVar[tuple[str, ...]] = ContextVar("workflow_stack", default=())


class WorkflowEngine:
    def __init__(self, db: Session) -> None:
        self.db = db

    def ensure_predefined_workflows(self) -> list[Workflow]:
        try:
            return self._sync_predefined_workflows()
        except IntegrityError:
            # Another job/request seeded the same workflow codes concurrently
            # (fresh database + parallel processing). Their rows are fine to use.
            self.db.rollback()
            return self._sync_predefined_workflows()

    def _sync_predefined_workflows(self) -> list[Workflow]:
        workflows: list[Workflow] = []
        now = datetime.now(timezone.utc)
        for definition in PREDEFINED_WORKFLOWS:
            validate_definition(definition)
            existing = self.db.scalar(
                select(Workflow).where(Workflow.code == definition["code"])
            )
            if existing is None:
                existing = Workflow(
                    code=definition["code"],
                    name=definition["name"],
                    description=definition["description"],
                    trigger_type=definition["trigger_type"],
                    status=WorkflowStatus.ACTIVE.value,
                    created_at=now,
                    updated_at=now,
                )
                self.db.add(existing)
            else:
                existing.name = definition["name"]
                existing.description = definition["description"]
                existing.trigger_type = definition["trigger_type"]
                existing.updated_at = now
            workflows.append(existing)
        self.db.commit()
        for workflow in workflows:
            self.db.refresh(workflow)
        return workflows

    def list_workflows(self) -> list[Workflow]:
        self.ensure_predefined_workflows()
        return list(
            self.db.scalars(select(Workflow).order_by(Workflow.name.asc())).all()
        )

    def get_workflow(self, workflow_id: uuid.UUID) -> Workflow:
        self.ensure_predefined_workflows()
        workflow = self.db.get(Workflow, workflow_id)
        if workflow is None:
            raise AppError("Workflow not found.", status_code=404)
        return workflow

    def get_workflow_by_code(self, code: str) -> Workflow | None:
        self.ensure_predefined_workflows()
        return self.db.scalar(select(Workflow).where(Workflow.code == code))

    def handle_event(
        self,
        *,
        trigger_event: str,
        entity_type: str,
        entity_id: str | uuid.UUID,
        metadata: dict[str, Any] | None = None,
        force: bool = False,
    ) -> list[dict[str, Any]]:
        if trigger_event not in ALLOWED_TRIGGER_TYPES:
            raise AppError(f"Unsupported trigger event: {trigger_event}", status_code=400)

        depth = _workflow_depth.get()
        if depth >= settings.WORKFLOW_MAX_DEPTH:
            logger.warning(
                "Workflow depth limit reached trigger=%s entity=%s/%s depth=%s",
                trigger_event,
                entity_type,
                entity_id,
                depth,
            )
            return [
                {
                    "status": "skipped",
                    "reason": "max_workflow_depth_reached",
                    "trigger_event": trigger_event,
                }
            ]

        self.ensure_predefined_workflows()
        workflows = self.db.scalars(
            select(Workflow).where(
                Workflow.trigger_type == trigger_event,
                Workflow.status == WorkflowStatus.ACTIVE.value,
            )
        ).all()

        results: list[dict[str, Any]] = []
        for workflow in workflows:
            results.append(
                self.trigger_workflow(
                    workflow.id,
                    trigger_event=trigger_event,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    metadata=metadata,
                    force=force,
                )
            )
        return results

    def trigger_workflow(
        self,
        workflow_id: uuid.UUID,
        *,
        trigger_event: str | None = None,
        entity_type: str,
        entity_id: str | uuid.UUID,
        metadata: dict[str, Any] | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        workflow = self.get_workflow(workflow_id)
        event = trigger_event or workflow.trigger_type
        if event not in ALLOWED_TRIGGER_TYPES:
            raise AppError(f"Unsupported trigger event: {event}", status_code=400)
        if workflow.trigger_type != event and not force:
            raise AppError(
                f"Workflow '{workflow.name}' is not configured for trigger '{event}'.",
                status_code=400,
            )
        if workflow.status != WorkflowStatus.ACTIVE.value:
            raise AppError("Workflow is disabled.", status_code=400)

        definition = get_definition_by_code(workflow.code)
        if definition is None:
            raise AppError("Workflow definition is not registered.", status_code=400)
        validate_definition(definition)

        entity_id_str = str(entity_id)
        stack = _workflow_stack.get()
        if workflow.code in stack:
            now = datetime.now(timezone.utc)
            skipped = WorkflowExecution(
                workflow_id=workflow.id,
                trigger_event=event,
                entity_type=entity_type,
                entity_id=entity_id_str,
                status=WorkflowExecutionStatus.SKIPPED.value,
                started_at=now,
                completed_at=now,
                execution_metadata={"reason": "recursive_workflow_blocked"},
            )
            self.db.add(skipped)
            self.db.commit()
            self.db.refresh(skipped)
            return self._execution_payload(skipped, workflow)

        if settings.WORKFLOW_DEDUP_ENABLED and not force:
            existing = self.db.scalar(
                select(WorkflowExecution)
                .where(
                    WorkflowExecution.workflow_id == workflow.id,
                    WorkflowExecution.trigger_event == event,
                    WorkflowExecution.entity_type == entity_type,
                    WorkflowExecution.entity_id == entity_id_str,
                    WorkflowExecution.status.in_(
                        [
                            WorkflowExecutionStatus.RUNNING.value,
                            WorkflowExecutionStatus.COMPLETED.value,
                        ]
                    ),
                )
                .order_by(WorkflowExecution.started_at.desc())
            )
            if existing is not None:
                payload = self._execution_payload(existing, workflow)
                payload["reason"] = "duplicate_execution_prevented"
                return payload

        depth_token = _workflow_depth.set(_workflow_depth.get() + 1)
        stack_token = _workflow_stack.set(stack + (workflow.code,))
        try:
            return self._execute(
                workflow=workflow,
                definition=definition,
                trigger_event=event,
                entity_type=entity_type,
                entity_id=entity_id_str,
                metadata=metadata or {},
            )
        finally:
            _workflow_depth.reset(depth_token)
            _workflow_stack.reset(stack_token)

    def _execute(
        self,
        *,
        workflow: Workflow,
        definition: dict[str, Any],
        trigger_event: str,
        entity_type: str,
        entity_id: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        execution = WorkflowExecution(
            workflow_id=workflow.id,
            trigger_event=trigger_event,
            entity_type=entity_type,
            entity_id=entity_id,
            status=WorkflowExecutionStatus.RUNNING.value,
            started_at=now,
            execution_metadata={"input": metadata},
        )
        self.db.add(execution)
        self.db.flush()

        ctx = build_context(
            self.db,
            trigger_event=trigger_event,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata=metadata,
        )

        try:
            conditions_ok, condition_notes = evaluate_conditions(
                list(definition.get("conditions") or []),
                ctx,
                mode=definition.get("condition_mode") or "all",
            )
            ctx.notes.extend(condition_notes)
            self._record_step(
                execution,
                step_name="evaluate_conditions",
                step_type="condition",
                status=(
                    WorkflowStepStatus.COMPLETED.value
                    if conditions_ok
                    else WorkflowStepStatus.SKIPPED.value
                ),
                result={"passed": conditions_ok, "notes": condition_notes},
            )

            if not conditions_ok:
                execution.status = WorkflowExecutionStatus.SKIPPED.value
                execution.completed_at = datetime.now(timezone.utc)
                execution.execution_metadata = {
                    **(execution.execution_metadata or {}),
                    "context": ctx.as_metadata(),
                    "reason": "conditions_not_met",
                }
                self.db.commit()
                return self._execution_payload(execution, workflow)

            for action in definition.get("actions") or []:
                self._run_action(execution, action, ctx)
                if execution.status == WorkflowExecutionStatus.FAILED.value:
                    break

            if execution.status == WorkflowExecutionStatus.RUNNING.value:
                execution.status = WorkflowExecutionStatus.COMPLETED.value
            execution.completed_at = datetime.now(timezone.utc)
            execution.execution_metadata = {
                **(execution.execution_metadata or {}),
                "context": ctx.as_metadata(),
            }
            self.db.commit()
            self.db.refresh(execution)
            return self._execution_payload(execution, workflow)
        except Exception as exc:
            logger.exception("Workflow execution failed code=%s", workflow.code)
            try:
                self.db.rollback()
            except Exception:
                pass
            failed = WorkflowExecution(
                workflow_id=workflow.id,
                trigger_event=trigger_event,
                entity_type=entity_type,
                entity_id=entity_id,
                status=WorkflowExecutionStatus.FAILED.value,
                started_at=now,
                completed_at=datetime.now(timezone.utc),
                error_message=str(exc) if str(exc) else "Workflow execution failed.",
                execution_metadata={"reason": "unexpected_failure"},
            )
            self.db.add(failed)
            self.db.commit()
            self.db.refresh(failed)
            return self._execution_payload(failed, workflow)

    def _run_action(
        self,
        execution: WorkflowExecution,
        action: dict[str, Any],
        ctx: WorkflowContext,
    ) -> None:
        action_type = action.get("type")
        step_name = action.get("name") or action_type
        if action_type not in ALLOWED_ACTION_TYPES:
            raise AppError(f"Unsupported workflow action: {action_type}", status_code=400)

        when = action.get("when") or {}
        if when:
            if "validation_status" in when and ctx.validation_status != when["validation_status"]:
                self._record_step(
                    execution,
                    step_name=step_name,
                    step_type=action_type,
                    status=WorkflowStepStatus.SKIPPED.value,
                    result={"reason": "when_condition_not_met", "when": when},
                )
                return

        started = datetime.now(timezone.utc)
        step = WorkflowStepExecution(
            workflow_execution_id=execution.id,
            step_name=step_name,
            step_type=action_type,
            status=WorkflowStepStatus.RUNNING.value,
            started_at=started,
        )
        self.db.add(step)
        self.db.flush()

        try:
            result = self._dispatch_action(action_type, action.get("params") or {}, ctx)
            step.status = WorkflowStepStatus.COMPLETED.value
            step.result = result
            step.completed_at = datetime.now(timezone.utc)
            self.db.flush()
        except Exception as exc:
            step.status = WorkflowStepStatus.FAILED.value
            step.error_message = str(exc) if str(exc) else "Step failed."
            step.completed_at = datetime.now(timezone.utc)
            execution.status = WorkflowExecutionStatus.FAILED.value
            execution.error_message = step.error_message
            self.db.flush()

    def _dispatch_action(
        self,
        action_type: str,
        params: dict[str, Any],
        ctx: WorkflowContext,
    ) -> dict[str, Any]:
        if action_type == "run_validation":
            return self._action_run_validation(ctx)
        if action_type == "create_review":
            return self._action_create_review(params, ctx)
        if action_type == "record_result":
            note = {
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "context": ctx.as_metadata(),
            }
            ctx.notes.append("result_recorded")
            return note
        if action_type == "mark_workflow_completed":
            return {"marked_completed": True}
        raise AppError(f"Unsupported workflow action: {action_type}", status_code=400)

    def _action_run_validation(self, ctx: WorkflowContext) -> dict[str, Any]:
        if ctx.invoice is None or ctx.related_purchase_order is None:
            raise AppError(
                "Invoice and related purchase order are required for validation.",
                status_code=400,
            )

        from app.models.validation import DocumentValidation

        response: ValidationResponse = ValidationService(self.db).validate_invoice_against_po(
            ctx.invoice.id,
            ctx.related_purchase_order.id,
            commit=False,
        )
        ctx.validation_status = response.status
        ctx.validation = self.db.get(DocumentValidation, response.id)
        ctx.notes.append(f"validation_status={response.status}")
        safe_dispatch_workflow_event(
            self.db,
            trigger_event="validation_completed",
            entity_type="validation",
            entity_id=response.id,
            metadata={"status": response.status, "source": "workflow_action"},
        )
        return {
            "validation_id": str(response.id),
            "status": response.status,
            "mismatch_summary": response.mismatch_summary,
        }

    def _action_create_review(self, params: dict[str, Any], ctx: WorkflowContext) -> dict[str, Any]:
        document_id = ctx.document.id if ctx.document else None
        if document_id is None and ctx.invoice is not None:
            document_id = ctx.invoice.document_id
        if document_id is None:
            raise AppError("Document is required to create a review.", status_code=400)

        reason = params.get("reason") or ReviewReason.LOW_CLASSIFICATION_CONFIDENCE.value
        # Prefer extraction reason when only extraction confidence failed
        if reason == ReviewReason.LOW_CLASSIFICATION_CONFIDENCE.value:
            class_low = (
                ctx.document is not None
                and ctx.document.classification_confidence is not None
                and ctx.document.classification_confidence < settings.WORKFLOW_CONFIDENCE_THRESHOLD
            )
            extraction_confidence = None
            if ctx.invoice is not None:
                extraction_confidence = ctx.invoice.extraction_confidence
            elif ctx.purchase_order is not None:
                extraction_confidence = ctx.purchase_order.extraction_confidence
            extraction_low = (
                extraction_confidence is not None
                and extraction_confidence < settings.WORKFLOW_CONFIDENCE_THRESHOLD
            )
            if extraction_low and not class_low:
                reason = ReviewReason.LOW_EXTRACTION_CONFIDENCE.value

        if reason not in {item.value for item in ReviewReason}:
            raise AppError(f"Invalid review reason for workflow: {reason}", status_code=400)

        priority = params.get("priority") or ReviewPriority.MEDIUM.value
        details = params.get("details") or "Created by controlled workflow engine."
        if ctx.validation_status == "mismatch" and ctx.validation and ctx.validation.mismatch_summary:
            details = ctx.validation.mismatch_summary

        review = DocumentReviewService(self.db).create_review_if_needed(
            document_id=document_id,
            reason=reason,
            details=details,
            priority=priority,
        )
        self.db.flush()
        return {
            "review_id": str(review.id) if review else None,
            "created_or_reused": True,
            "reason": reason,
        }

    def _record_step(
        self,
        execution: WorkflowExecution,
        *,
        step_name: str,
        step_type: str,
        status: str,
        result: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        step = WorkflowStepExecution(
            workflow_execution_id=execution.id,
            step_name=step_name,
            step_type=step_type,
            status=status,
            started_at=now,
            completed_at=now,
            result=result,
            error_message=error_message,
        )
        self.db.add(step)
        self.db.flush()

    def list_executions(
        self,
        workflow_id: uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        from sqlalchemy import func

        workflow = self.get_workflow(workflow_id)
        if page < 1:
            raise AppError("page must be >= 1.", status_code=400)
        if page_size < 1 or page_size > 100:
            raise AppError("page_size must be between 1 and 100.", status_code=400)

        total = (
            self.db.scalar(
                select(func.count())
                .select_from(WorkflowExecution)
                .where(WorkflowExecution.workflow_id == workflow.id)
            )
            or 0
        )
        rows = self.db.scalars(
            select(WorkflowExecution)
            .where(WorkflowExecution.workflow_id == workflow.id)
            .order_by(WorkflowExecution.started_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return {
            "workflow_id": workflow.id,
            "items": [self._execution_payload(row, workflow) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def get_execution(self, execution_id: uuid.UUID) -> dict[str, Any]:
        execution = self.db.get(WorkflowExecution, execution_id)
        if execution is None:
            raise AppError("Workflow execution not found.", status_code=404)
        workflow = self.db.get(Workflow, execution.workflow_id)
        return self._execution_payload(execution, workflow)

    def _execution_payload(
        self,
        execution: WorkflowExecution,
        workflow: Workflow | None,
    ) -> dict[str, Any]:
        steps = list(
            self.db.scalars(
                select(WorkflowStepExecution)
                .where(WorkflowStepExecution.workflow_execution_id == execution.id)
                .order_by(WorkflowStepExecution.started_at.asc())
            ).all()
        )
        definition = get_definition_by_code(workflow.code) if workflow else None
        return {
            "id": execution.id,
            "workflow_id": execution.workflow_id,
            "workflow_code": workflow.code if workflow else None,
            "workflow_name": workflow.name if workflow else None,
            "trigger_event": execution.trigger_event,
            "entity_type": execution.entity_type,
            "entity_id": execution.entity_id,
            "status": execution.status,
            "started_at": execution.started_at,
            "completed_at": execution.completed_at,
            "error_message": execution.error_message,
            "execution_metadata": execution.execution_metadata,
            "allowed_actions": (
                [action["type"] for action in (definition or {}).get("actions") or []]
                if definition
                else []
            ),
            "steps": [
                {
                    "id": step.id,
                    "step_name": step.step_name,
                    "step_type": step.step_type,
                    "status": step.status,
                    "started_at": step.started_at,
                    "completed_at": step.completed_at,
                    "result": step.result,
                    "error_message": step.error_message,
                }
                for step in steps
            ],
            "reason": (execution.execution_metadata or {}).get("reason")
            if isinstance(execution.execution_metadata, dict)
            else None,
        }


def safe_dispatch_workflow_event(
    db: Session,
    *,
    trigger_event: str,
    entity_type: str,
    entity_id: str | uuid.UUID,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Best-effort event dispatch that never breaks the calling business flow."""
    try:
        WorkflowEngine(db).handle_event(
            trigger_event=trigger_event,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata=metadata,
        )
    except Exception:
        logger.exception(
            "Workflow event dispatch failed trigger=%s entity=%s/%s",
            trigger_event,
            entity_type,
            entity_id,
        )
        # Leave the session usable for the caller (e.g. the processing job must still be
        # marked completed/failed); without this every later query raises PendingRollbackError.
        try:
            db.rollback()
        except Exception:
            logger.exception("Rollback after workflow dispatch failure also failed")
