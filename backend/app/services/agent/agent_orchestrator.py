"""Bounded multi-step controlled agent orchestrator."""

from __future__ import annotations

from typing import Any
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppError
from app.models.agent_run import AgentRun
from app.models.user import User
from app.schemas.agent import (
    AgentAskRequest,
    AgentAskResponse,
    AgentEvidenceItem,
    AgentRunListResponse,
    AgentRunSummary,
    AgentStepResult,
)
from app.services.agent.agent_context import AgentContext
from app.services.agent.agent_planner import AgentPlan, DeterministicAgentPlanner, PlannedStep
from app.services.agent.agent_policy import AgentPolicy
from app.services.agent.agent_registry import AgentToolRegistry
from app.services.agent.agent_tools import _summarize, build_default_registry
from app.services.audit_service import AuditService


class AgentOrchestrator:
    def __init__(
        self,
        db: Session,
        registry: AgentToolRegistry | None = None,
        planner: DeterministicAgentPlanner | None = None,
    ) -> None:
        self.db = db
        self.registry = registry or build_default_registry(db)
        self.planner = planner or DeterministicAgentPlanner(db)
        self.audit = AuditService(db)

    def ask(self, payload: AgentAskRequest, *, user: User) -> AgentAskResponse:
        AgentPolicy.assert_can_use_agent(user)

        question = (payload.question or "").strip()
        max_len = settings.AGENT_MAX_QUESTION_LENGTH
        if not question:
            raise AppError("Question is required.", status_code=400)
        if len(question) > max_len:
            raise AppError(f"Question exceeds the maximum length of {max_len} characters.", status_code=400)

        max_steps = self._resolve_max_steps(payload.max_steps)
        conversation_id = payload.conversation_id or uuid.uuid4()

        ctx = AgentContext(
            user=user,
            question=question,
            conversation_id=conversation_id,
            max_steps=max_steps,
        )

        self.audit.log(
            action="agent_ask_started",
            user_id=user.id,
            resource_type="agent",
            resource_id=conversation_id,
            details={"question_length": len(question), "max_steps": max_steps},
        )

        plan = self.planner.plan(question)
        ctx.resolved.update(plan.resolved)

        if plan.status != "ready" or not plan.steps:
            response = AgentAskResponse(
                answer=plan.explanation
                or "This request is not supported by the controlled agent planner.",
                status="unsupported",
                steps=[],
                evidence=[],
                tools_used=[],
                warnings=ctx.warnings,
                conversation_id=conversation_id,
            )
            run = self._persist_run(ctx, response)
            response.run_id = run.id
            self.audit.log(
                action="agent_ask_unsupported",
                user_id=user.id,
                resource_type="agent",
                resource_id=run.id,
                details={"intent": plan.intent},
            )
            return response

        consecutive_failures = 0
        for planned in plan.steps:
            if ctx.step_count >= ctx.max_steps:
                ctx.add_warning(f"Stopped after reaching max_steps={ctx.max_steps}.")
                break
            step_result = self._execute_step(ctx, planned)
            if step_result["status"] == "failed":
                consecutive_failures += 1
                if consecutive_failures >= 2:
                    ctx.add_warning("Stopped after repeated tool failures.")
                    break
            else:
                consecutive_failures = 0
            if step_result["status"] == "permission_denied":
                ctx.add_warning(f"Permission denied for tool '{planned.tool_name}'.")
                break

        answer, status = self._synthesize(ctx, plan)
        response = AgentAskResponse(
            answer=answer,
            status=status,
            steps=[AgentStepResult(**step) for step in ctx.steps],
            evidence=[AgentEvidenceItem(**item) for item in ctx.evidence],
            tools_used=list(ctx.tools_used),
            warnings=list(ctx.warnings),
            conversation_id=conversation_id,
        )
        run = self._persist_run(ctx, response)
        response.run_id = run.id
        self.audit.log(
            action="agent_ask_completed",
            user_id=user.id,
            resource_type="agent",
            resource_id=run.id,
            details={
                "status": status,
                "step_count": ctx.step_count,
                "tools_used": ctx.tools_used,
                "intent": plan.intent,
            },
        )
        return response

    def list_runs(
        self,
        *,
        user: User,
        conversation_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> AgentRunListResponse:
        AgentPolicy.assert_can_use_agent(user)
        page = max(1, page)
        page_size = min(100, max(1, page_size))
        query = select(AgentRun).where(AgentRun.user_id == user.id)
        if conversation_id is not None:
            query = query.where(AgentRun.conversation_id == conversation_id)
        total = self.db.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = list(
            self.db.scalars(
                query.order_by(AgentRun.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        return AgentRunListResponse(
            items=[
                AgentRunSummary(
                    id=row.id,
                    conversation_id=row.conversation_id,
                    question=row.question,
                    status=row.status,
                    answer=row.answer,
                    tools_used=list(row.tools_used or []),
                    step_count=row.step_count,
                    created_at=row.created_at,
                )
                for row in rows
            ],
            total=int(total),
            page=page,
            page_size=page_size,
        )

    def _resolve_max_steps(self, requested: int | None) -> int:
        default = max(1, min(settings.AGENT_MAX_STEPS, settings.AGENT_HARD_MAX_STEPS))
        hard = max(1, min(10, settings.AGENT_HARD_MAX_STEPS))
        if requested is None:
            return default
        return max(1, min(int(requested), hard))

    def _execute_step(self, ctx: AgentContext, planned: PlannedStep) -> dict[str, Any]:
        ctx.step_count += 1
        tool = self.registry.get(planned.tool_name)
        step_number = ctx.step_count
        if tool is None:
            record = {
                "step_number": step_number,
                "tool_name": planned.tool_name,
                "purpose": planned.purpose,
                "status": "failed",
                "concise_result_summary": "Tool is not registered.",
            }
            ctx.steps.append(record)
            ctx.add_warning(f"Unregistered tool '{planned.tool_name}'.")
            return record

        try:
            AgentPolicy.assert_can_run_tool(ctx.user, tool)
        except AppError as exc:
            record = {
                "step_number": step_number,
                "tool_name": planned.tool_name,
                "purpose": planned.purpose,
                "status": "permission_denied",
                "concise_result_summary": exc.message,
            }
            ctx.steps.append(record)
            return record

        arguments = self._bind_arguments(ctx, planned.arguments)
        try:
            assert tool.handler is not None
            result = tool.handler(**arguments)
            summary = ""
            if isinstance(result, dict):
                summary = str(result.get("summary") or _summarize(result))
                ctx.add_evidence(
                    source=planned.tool_name,
                    summary=summary,
                    details={
                        k: v
                        for k, v in result.items()
                        if k not in {"raw", "rag", "sql_result", "investigation", "field_intelligence"}
                        or k == "summary"
                    }
                    if len(str(result)) < 4000
                    else {"summary": summary},
                )
                # Capture related IDs for later steps
                related = result.get("related") if isinstance(result.get("related"), dict) else None
                if related:
                    ctx.resolved.update({k: v for k, v in related.items() if v is not None})
                invoice = result.get("invoice")
                if isinstance(invoice, dict):
                    if invoice.get("id"):
                        ctx.resolved["invoice_id"] = str(invoice["id"])
                    if invoice.get("document_id"):
                        ctx.resolved["document_id"] = str(invoice["document_id"])
            else:
                summary = _summarize(result)
                ctx.add_evidence(source=planned.tool_name, summary=summary)

            ctx.record_tool(planned.tool_name)
            record = {
                "step_number": step_number,
                "tool_name": planned.tool_name,
                "purpose": planned.purpose,
                "status": "completed",
                "concise_result_summary": summary[:500],
            }
            ctx.steps.append(record)
            return record
        except AppError as exc:
            record = {
                "step_number": step_number,
                "tool_name": planned.tool_name,
                "purpose": planned.purpose,
                "status": "failed",
                "concise_result_summary": exc.message[:500],
            }
            ctx.steps.append(record)
            ctx.add_warning(exc.message)
            return record
        except Exception as exc:  # noqa: BLE001
            record = {
                "step_number": step_number,
                "tool_name": planned.tool_name,
                "purpose": planned.purpose,
                "status": "failed",
                "concise_result_summary": f"Tool execution failed: {str(exc)[:200]}",
            }
            ctx.steps.append(record)
            ctx.add_warning(record["concise_result_summary"])
            return record

    def _bind_arguments(self, ctx: AgentContext, arguments: dict[str, Any]) -> dict[str, Any]:
        bound = dict(arguments or {})
        # Fill placeholders from resolved context without inventing new tools
        for key in ("document_id", "invoice_id", "purchase_order_id", "review_id", "match_id"):
            if key not in bound and key in ctx.resolved:
                bound[key] = ctx.resolved[key]
        # validate_invoice_po needs both IDs when available
        if "invoice_id" in bound and isinstance(bound["invoice_id"], str):
            try:
                bound["invoice_id"] = uuid.UUID(bound["invoice_id"])
            except ValueError as exc:
                raise AppError("Invalid invoice_id.", status_code=400) from exc
        if "purchase_order_id" in bound and isinstance(bound["purchase_order_id"], str):
            try:
                bound["purchase_order_id"] = uuid.UUID(bound["purchase_order_id"])
            except ValueError as exc:
                raise AppError("Invalid purchase_order_id.", status_code=400) from exc
        if "document_id" in bound and isinstance(bound["document_id"], str):
            try:
                bound["document_id"] = uuid.UUID(bound["document_id"])
            except ValueError as exc:
                raise AppError("Invalid document_id.", status_code=400) from exc
        return bound

    def _synthesize(self, ctx: AgentContext, plan: AgentPlan) -> tuple[str, str]:
        completed = [s for s in ctx.steps if s["status"] == "completed"]
        if not completed and any(s["status"] == "permission_denied" for s in ctx.steps):
            return (
                "The controlled agent could not continue because a required tool permission was denied.",
                "permission_denied",
            )
        if not completed:
            return (
                "The controlled agent could not gather enough evidence to answer.",
                "failed",
            )

        lines = [
            f"Intent: {plan.intent.replace('_', ' ')}.",
            f"Completed {len(completed)} of {len(ctx.steps)} planned step(s).",
        ]
        for item in ctx.evidence[:8]:
            lines.append(f"- [{item['source']}] {item['summary']}")
        if ctx.warnings:
            lines.append("Warnings: " + "; ".join(ctx.warnings[:5]))
        if ctx.step_count >= ctx.max_steps and len(plan.steps) > len(ctx.steps):
            status = "partial"
            lines.insert(1, "Execution stopped at the configured step limit.")
        else:
            status = "completed"
        # Prefer RAG/SQL/investigation natural answers when present
        for step in reversed(ctx.steps):
            if step["status"] != "completed":
                continue
            if step["tool_name"] in {"ask_knowledge", "execute_safe_sql_question", "run_investigation"}:
                summary = step["concise_result_summary"]
                if summary and summary not in {"No data."}:
                    lines.insert(1, summary)
                    break
        return ("\n".join(lines), status)

    def _persist_run(self, ctx: AgentContext, response: AgentAskResponse) -> AgentRun:
        row = AgentRun(
            conversation_id=response.conversation_id,
            user_id=ctx.user.id,
            question=ctx.question[:2000],
            status=response.status,
            answer=response.answer[:10000],
            steps_json=[s.model_dump(mode="json") for s in response.steps],
            evidence_json=[e.model_dump(mode="json") for e in response.evidence],
            tools_used=list(response.tools_used),
            warnings_json=list(response.warnings),
            step_count=ctx.step_count,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row
