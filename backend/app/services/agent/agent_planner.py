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


_AMOUNT_OVER = re.compile(
    r"\b(?:over|above|greater than|>)\s*\$?\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)\b",
    re.IGNORECASE,
)

_FILLER_INVOICE_TOKENS = frozenset(
    {
        "the",
        "a",
        "an",
        "is",
        "to",
        "for",
        "with",
        "from",
        "and",
        "or",
        "why",
        "how",
        "what",
        "needs",
        "need",
        "attention",
        "review",
        "investigate",
        "investigation",
        "estigate",
        "invoice",
        "invoices",
    }
)


def _extract_invoice_number(question: str) -> str | None:
    """
    Extract an invoice identifier from natural language.

    Prioritizes explicit INV-… / INV/… patterns and never treats substrings of
    words like "investigate", "invoice", or "investigation" as invoice numbers.
    """
    text = question or ""

    # Explicit identifiers: INV-1827, INV1001, INV/2026/001
    inv_style = re.search(
        r"\b(INV[-_/]?[0-9][A-Za-z0-9\-/]{0,40})\b",
        text,
        flags=re.IGNORECASE,
    )
    if inv_style:
        raw = re.sub(r"\s+", "", inv_style.group(1))
        safe = re.sub(r"[^A-Za-z0-9\-/]", "", raw)
        if len(safe) >= 3 and safe[:3].upper() == "INV":
            return "INV" + safe[3:]
        return safe or None

    # Labeled forms: "invoice INV-1827", "invoice number 1001", "invoice #ABC-9"
    labeled = re.search(
        r"\binvoice(?:\s+number)?[\s#:.-]+([A-Za-z0-9][A-Za-z0-9\-/]{1,40})\b",
        text,
        flags=re.IGNORECASE,
    )
    if labeled:
        candidate = labeled.group(1).strip()
        lower_candidate = candidate.lower()
        if lower_candidate in _FILLER_INVOICE_TOKENS:
            return None
        # Require an identifier-like token (digit and/or separator), not English words.
        if not re.search(r"[0-9]", candidate) and not re.search(r"[-/]", candidate):
            return None
        if lower_candidate.isalpha():
            return None
        safe = re.sub(r"[^A-Za-z0-9\-/]", "", candidate)
        return safe or None

    return None


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

        # A2. Investigate why a specific invoice needs attention / has issues
        # Prefer the read-only Investigation Agent for attention-style questions.
        if invoice_number and any(
            token in lower for token in ("attention", "flagged", "issues", "issue")
        ) and any(
            token in lower
            for token in ("investigate", "investigation", "why", "explain", "reason", "summarize")
        ):
            return self._plan_invoice_attention_via_investigation(q, invoice_number)

        # B. Investigate invoice X
        if invoice_number and any(
            token in lower for token in ("investigate", "investigation", "deep dive", "look into")
        ):
            return self._plan_invoice_investigation(invoice_number)

        # Generic invoice status / why without explicit investigate
        if invoice_number and any(
            token in lower for token in ("why", "status", "explain", "review", "attention")
        ):
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

        # Any other question the read-only Investigation planner understands
        # (review drivers, vendor issues, missing fields, low confidence, duplicates...).
        # Totals by vendor stay with the SQL tool, which returns the table directly.
        from app.services.investigation_planner import plan_investigation

        investigation = plan_investigation(q)
        if investigation.status == "ready" and investigation.template_id != "invoice_totals_by_vendor":
            return AgentPlan(
                status="ready",
                intent="general_investigation",
                steps=[
                    PlannedStep(
                        tool_name="run_investigation",
                        purpose=f"Run read-only investigation: {investigation.title}",
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

    def _plan_invoice_attention_via_investigation(
        self, question: str, invoice_number: str
    ) -> AgentPlan:
        """Route attention questions through the controlled Investigation Agent."""
        invoice = find_invoice_by_number(self.db, invoice_number)
        if invoice is None:
            return AgentPlan(
                status="unsupported",
                intent="invoice_attention_investigation",
                explanation=f"No invoice matching '{invoice_number}' was found.",
            )
        return AgentPlan(
            status="ready",
            intent="invoice_attention_investigation",
            resolved={
                "document_id": str(invoice.document_id),
                "invoice_id": str(invoice.id),
                "invoice_number": invoice_number,
            },
            steps=[
                PlannedStep(
                    "get_invoice",
                    "Confirm invoice record before investigation",
                    {"invoice_number": invoice_number},
                ),
                PlannedStep(
                    "run_investigation",
                    "Investigate why this invoice needs attention and summarize findings",
                    {"question": question},
                ),
            ],
            explanation=(
                f"Investigate invoice {invoice_number} via the read-only Investigation Agent."
            ),
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
