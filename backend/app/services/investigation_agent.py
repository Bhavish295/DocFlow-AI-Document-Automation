"""Read-only AI Investigation Agent orchestration."""

from __future__ import annotations

import logging
from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppError
from app.services.investigation_analysis import analyze_investigation_results
from app.services.investigation_planner import InvestigationPlan, plan_investigation
from app.services.sql_execution import execute_readonly_sql
from app.services.sql_guard import validate_readonly_sql

logger = logging.getLogger(__name__)


class InvestigationProvider(Protocol):
    """Optional provider hook for future non-deterministic planning."""

    def plan(self, question: str) -> InvestigationPlan:
        """Return an investigation plan for the question."""


class DeterministicInvestigationProvider:
    def plan(self, question: str) -> InvestigationPlan:
        return plan_investigation(question)


class InvestigationAgent:
    """Investigate business data using controlled multi-step read-only SQL."""

    def __init__(
        self,
        db: Session,
        provider: InvestigationProvider | None = None,
    ) -> None:
        self.db = db
        self.provider = provider or DeterministicInvestigationProvider()

    def investigate(self, question: str) -> dict[str, Any]:
        cleaned = (question or "").strip()
        logger.info("Investigation question received length=%s", len(cleaned))

        max_len = settings.SQL_MAX_QUESTION_LENGTH
        if not cleaned:
            return self._unsupported(
                cleaned,
                "Please enter an investigation question.",
            )
        if len(cleaned) > max_len:
            return {
                "question": cleaned,
                "status": "failed",
                "summary": f"Question exceeds the maximum length of {max_len} characters.",
                "findings": [],
                "evidence": [],
                "queries": [],
                "suggested_next_steps": [],
            }

        try:
            plan = self.provider.plan(cleaned)
        except Exception:
            logger.exception("Investigation planning failed")
            return {
                "question": cleaned,
                "status": "failed",
                "summary": "Investigation planning failed.",
                "findings": [],
                "evidence": [],
                "queries": [],
                "suggested_next_steps": [],
            }

        if plan.status != "ready" or not plan.queries:
            return self._unsupported(
                cleaned,
                plan.unsupported_message
                or "This investigation type is not supported.",
            )

        step_results: list[dict[str, Any]] = []
        query_summaries: list[dict[str, Any]] = []
        any_success = False

        for planned in plan.queries:
            # Never execute SQL that fails the shared Step 11 guard.
            validation = validate_readonly_sql(planned.sql)
            if not validation.valid or not validation.normalized_sql:
                logger.warning(
                    "Investigation SQL rejected by guard step=%s reason=%s",
                    planned.step_id,
                    validation.reason,
                )
                step_results.append(
                    {
                        "step_id": planned.step_id,
                        "question": planned.question,
                        "sql": planned.sql,
                        "analysis_key": planned.analysis_key,
                        "columns": [],
                        "rows": [],
                        "row_count": 0,
                        "error": validation.reason or "SQL rejected by safety guard.",
                    }
                )
                query_summaries.append(
                    {
                        "question": planned.question,
                        "sql": planned.sql,
                        "row_count": 0,
                        "status": "rejected",
                    }
                )
                continue

            try:
                execution = execute_readonly_sql(self.db, validation.normalized_sql)
                any_success = True
                step_results.append(
                    {
                        "step_id": planned.step_id,
                        "question": planned.question,
                        "sql": validation.normalized_sql,
                        "analysis_key": planned.analysis_key,
                        "columns": execution.columns,
                        "rows": execution.rows,
                        "row_count": execution.row_count,
                        "error": None,
                    }
                )
                query_summaries.append(
                    {
                        "question": planned.question,
                        "sql": validation.normalized_sql,
                        "row_count": execution.row_count,
                        "status": "success",
                    }
                )
            except AppError as exc:
                logger.warning(
                    "Investigation step execution failed step=%s",
                    planned.step_id,
                )
                step_results.append(
                    {
                        "step_id": planned.step_id,
                        "question": planned.question,
                        "sql": validation.normalized_sql,
                        "analysis_key": planned.analysis_key,
                        "columns": [],
                        "rows": [],
                        "row_count": 0,
                        "error": exc.message,
                    }
                )
                query_summaries.append(
                    {
                        "question": planned.question,
                        "sql": validation.normalized_sql,
                        "row_count": 0,
                        "status": "error",
                    }
                )
            except Exception:
                logger.exception("Unexpected investigation execution failure")
                step_results.append(
                    {
                        "step_id": planned.step_id,
                        "question": planned.question,
                        "sql": validation.normalized_sql,
                        "analysis_key": planned.analysis_key,
                        "columns": [],
                        "rows": [],
                        "row_count": 0,
                        "error": "execution_error",
                    }
                )
                query_summaries.append(
                    {
                        "question": planned.question,
                        "sql": validation.normalized_sql,
                        "row_count": 0,
                        "status": "error",
                    }
                )

        if not any_success:
            return {
                "question": cleaned,
                "status": "failed",
                "summary": (
                    "The investigation could not retrieve usable data. "
                    "No findings were generated."
                ),
                "findings": [],
                "evidence": [],
                "queries": query_summaries,
                "suggested_next_steps": list(plan.suggested_next_steps),
            }

        analysis = analyze_investigation_results(plan.template_id, step_results)
        summary = (
            f"Completed investigation '{plan.title}' using {len(query_summaries)} "
            f"read-only query step(s)."
        )
        logger.info(
            "Investigation completed template=%s steps=%s findings=%s",
            plan.template_id,
            len(query_summaries),
            len(analysis.findings),
        )
        return {
            "question": cleaned,
            "status": "completed",
            "summary": summary,
            "findings": [
                {
                    "title": finding.title,
                    "description": finding.description,
                    "type": finding.type,
                }
                for finding in analysis.findings
            ],
            "evidence": [
                {
                    "description": item.description,
                    "data": item.data,
                    "step_id": item.step_id,
                }
                for item in analysis.evidence
            ],
            "queries": query_summaries,
            "suggested_next_steps": list(plan.suggested_next_steps),
        }

    @staticmethod
    def _unsupported(question: str, message: str) -> dict[str, Any]:
        return {
            "question": question,
            "status": "unsupported",
            "summary": message,
            "findings": [],
            "evidence": [],
            "queries": [],
            "suggested_next_steps": [
                "Try a supported investigation such as review drivers, validation mismatches, "
                "vendor mismatch patterns, missing fields, low confidence, or documents needing attention.",
            ],
        }
