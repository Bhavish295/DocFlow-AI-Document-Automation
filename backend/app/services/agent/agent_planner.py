"""Deterministic planner — no LLM required."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

from sqlalchemy.orm import Session

from app.services.agent.agent_tools import find_document_id_for_invoice_number, find_invoice_by_number


@dataclass
class PlannedStep:
    tool_name: str
    purpose: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentPlan:
    status: str  # ready | unsupported
    intent: str
    steps: list[PlannedStep] = field(default_factory=list)
    explanation: str = ""
    resolved: dict[str, Any] = field(default_factory=dict)


_INVOICE_REF = re.compile(
    r"\b(?:invoice|inv)[\s#:.-]*([A-Za-z0-9][A-Za-z0-9\-/]{1,40})\b",
    re.IGNORECASE,
)
_AMOUNT_OVER = re.compile(
    r"\b(?:over|above|greater than|>)\s*\$?\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)\b",
    re.IGNORECASE,
)


def _extract_invoice_number(question: str) -> str | None:
    match = _INVOICE_REF.search(question or "")
    if not match:
        return None
    return match.group(1).strip()


def _extract_amount(question: str) -> str | None:
    match = _AMOUNT_OVER.search(question or "")
    if not match:
        return None
    return match.group(1).replace(",", "")


class DeterministicAgentPlanner:
    """Pattern-based multi-step planner. Does not guess unknown intents."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def plan(self, question: str) -> AgentPlan:
        q = (question or "").strip()
        if not q:
            return AgentPlan(
                status="unsupported",
                intent="empty",
                explanation="Please enter a question for the controlled agent.",
            )

        lower = q.lower()
        invoice_number = _extract_invoice_number(q)

        # A. Why is invoice X in review?
        if invoice_number and "review" in lower and any(
            token in lower for token in ("why", "reason", "explain", "because")
        ):
            return self._plan_review_explanation(invoice_number)

        # B. Investigate invoice X
        if invoice_number and any(
            token in lower for token in ("investigate", "investigation", "deep dive", "look into")
        ):
            return self._plan_invoice_investigation(invoice_number)

        # Generic invoice status / why without explicit investigate
        if invoice_number and any(token in lower for token in ("why", "status", "explain", "review")):
            return self._plan_review_explanation(invoice_number)

        # C. Find unusual invoices
        if any(
            phrase in lower
            for phrase in (
                "unusual invoice",
                "unusual invoices",
                "anomalous invoice",
                "anomalous invoices",
                "find unusual",
                "suspicious invoice",
                "suspicious invoices",
            )
        ) or (re.search(r"\bunusual\b", lower) and "invoice" in lower):
            return self._plan_unusual_invoices()

        # D. Find invoices over N and explain suspicious ones
        amount = _extract_amount(q)
        if amount and "invoice" in lower and any(
            token in lower for token in ("over", "above", "greater", "suspicious", "explain", "unusual")
        ):
            return self._plan_high_value_suspicious(amount, q)

        # Investigation-style without invoice number
        if any(token in lower for token in ("investigate", "why are invoices", "which vendors", "require attention")):
            return AgentPlan(
                status="ready",
                intent="general_investigation",
                steps=[
                    PlannedStep(
                        tool_name="run_investigation",
                        purpose="Run read-only multi-query investigation",
                        arguments={"question": q},
                    )
                ],
            )

        # Business SQL-style questions
        if any(
            token in lower
            for token in (
                "how many",
                "count",
                "total amount",
                "sum of",
                "list invoices",
                "show invoices",
                "average",
                "vendor",
            )
        ) and any(token in lower for token in ("invoice", "purchase order", "vendor", "validation", "review")):
            return AgentPlan(
                status="ready",
                intent="safe_sql",
                steps=[
                    PlannedStep(
                        tool_name="execute_safe_sql_question",
                        purpose="Answer using the read-only SQL safety layer",
                        arguments={"question": q},
                    )
                ],
            )

        # Document knowledge / RAG
        if any(
            token in lower
            for token in (
                "document",
                "contract",
                "payment terms",
                "what does",
                "according to",
                "mentioned",
                "policy",
            )
        ):
            return AgentPlan(
                status="ready",
                intent="knowledge",
                steps=[
                    PlannedStep(
                        tool_name="ask_knowledge",
                        purpose="Answer from indexed document knowledge",
                        arguments={"question": q},
                    )
                ],
            )

        # Anomaly summary short-cut
        if "anomal" in lower:
            return self._plan_unusual_invoices()

        return AgentPlan(
            status="unsupported",
            intent="unknown",
            explanation=(
                "I could not safely map that request to a registered tool plan. "
                "Try asking about a specific invoice (e.g. why INV-1827 is in review), "
                "unusual invoices, a business data count, or a document knowledge question."
            ),
        )

    def _plan_review_explanation(self, invoice_number: str) -> AgentPlan:
        document_id = find_document_id_for_invoice_number(self.db, invoice_number)
        if document_id is None:
            return AgentPlan(
                status="unsupported",
                intent="review_explanation",
                explanation=f"No invoice matching '{invoice_number}' was found.",
            )
        doc_id = str(document_id)
        return AgentPlan(
            status="ready",
            intent="review_explanation",
            resolved={"document_id": doc_id, "invoice_number": invoice_number},
            steps=[
                PlannedStep("get_invoice", "Load invoice record", {"invoice_number": invoice_number}),
                PlannedStep("get_field_intelligence", "Inspect field intelligence findings", {"document_id": doc_id}),
                PlannedStep("list_validation_results", "Collect validation results", {"page": 1, "page_size": 20}),
                PlannedStep("get_review", "Load review details for the document", {"document_id": doc_id}),
                PlannedStep("get_duplicate_findings", "Check duplicate findings", {"document_id": doc_id}),
            ],
        )

    def _plan_invoice_investigation(self, invoice_number: str) -> AgentPlan:
        invoice = find_invoice_by_number(self.db, invoice_number)
        if invoice is None:
            return AgentPlan(
                status="unsupported",
                intent="invoice_investigation",
                explanation=f"No invoice matching '{invoice_number}' was found.",
            )
        doc_id = str(invoice.document_id)
        steps = [
            PlannedStep("get_invoice", "Locate invoice data", {"invoice_number": invoice_number}),
            PlannedStep("resolve_related_po_grn", "Find related PO identifiers", {"document_id": doc_id}),
            PlannedStep("get_field_intelligence", "Field intelligence", {"document_id": doc_id}),
            PlannedStep("list_validation_results", "Validation results", {"page": 1, "page_size": 20}),
            PlannedStep("get_three_way_match", "Three-way match context", {}),
            PlannedStep("get_review", "Review status", {"document_id": doc_id}),
            PlannedStep("get_document_anomaly", "Anomaly score", {"document_id": doc_id}),
            PlannedStep("check_document_duplicates", "Duplicate findings", {"document_id": doc_id}),
        ]
        return AgentPlan(
            status="ready",
            intent="invoice_investigation",
            resolved={
                "document_id": doc_id,
                "invoice_id": str(invoice.id),
                "invoice_number": invoice_number,
            },
            steps=steps,
        )

    def _plan_unusual_invoices(self) -> AgentPlan:
        return AgentPlan(
            status="ready",
            intent="unusual_invoices",
            steps=[
                PlannedStep("get_anomaly_summary", "Load anomaly summary", {}),
                PlannedStep(
                    "search_documents",
                    "List recent invoice documents",
                    {"document_type": "invoice", "page": 1, "page_size": 10},
                ),
                PlannedStep(
                    "run_investigation",
                    "Explain unusual invoice patterns from evidence",
                    {"question": "Which invoices look unusual or need attention?"},
                ),
            ],
        )

    def _plan_high_value_suspicious(self, amount: str, question: str) -> AgentPlan:
        sql_question = f"Find invoices with total amount over {amount}"
        return AgentPlan(
            status="ready",
            intent="high_value_suspicious",
            resolved={"amount_threshold": amount},
            steps=[
                PlannedStep(
                    "execute_safe_sql_question",
                    "Query invoices above the amount threshold",
                    {"question": sql_question},
                ),
                PlannedStep("get_anomaly_summary", "Load anomaly summary for suspicious context", {}),
                PlannedStep(
                    "run_investigation",
                    "Investigate suspicious high-value invoices",
                    {"question": question},
                ),
            ],
        )
