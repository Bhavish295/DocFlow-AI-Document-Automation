"""Deterministic workflow condition evaluation against application data."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import Document
from app.models.document_review import DocumentReview
from app.models.invoice import Invoice
from app.models.purchase_order import PurchaseOrder
from app.models.validation import DocumentValidation


@dataclass
class WorkflowContext:
    """Runtime context for condition evaluation and action execution."""

    db: Session
    trigger_event: str
    entity_type: str
    entity_id: str
    metadata: dict[str, Any] = field(default_factory=dict)
    document: Document | None = None
    invoice: Invoice | None = None
    purchase_order: PurchaseOrder | None = None
    related_purchase_order: PurchaseOrder | None = None
    validation: DocumentValidation | None = None
    review: DocumentReview | None = None
    validation_status: str | None = None
    notes: list[str] = field(default_factory=list)

    def as_metadata(self) -> dict[str, Any]:
        return {
            "trigger_event": self.trigger_event,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "document_id": str(self.document.id) if self.document else None,
            "invoice_id": str(self.invoice.id) if self.invoice else None,
            "purchase_order_id": (
                str(self.related_purchase_order.id)
                if self.related_purchase_order
                else (str(self.purchase_order.id) if self.purchase_order else None)
            ),
            "validation_id": str(self.validation.id) if self.validation else None,
            "validation_status": self.validation_status,
            "review_id": str(self.review.id) if self.review else None,
            "review_status": self.review.status if self.review else None,
            "notes": list(self.notes),
            **{k: v for k, v in self.metadata.items() if k not in {"notes"}},
        }


def build_context(
    db: Session,
    *,
    trigger_event: str,
    entity_type: str,
    entity_id: str,
    metadata: dict[str, Any] | None = None,
) -> WorkflowContext:
    ctx = WorkflowContext(
        db=db,
        trigger_event=trigger_event,
        entity_type=entity_type,
        entity_id=str(entity_id),
        metadata=dict(metadata or {}),
    )
    _hydrate_context(ctx)
    return ctx


def _parse_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def _hydrate_context(ctx: WorkflowContext) -> None:
    entity_uuid = _parse_uuid(ctx.entity_id)
    if ctx.entity_type == "document" and entity_uuid:
        ctx.document = ctx.db.get(Document, entity_uuid)
        if ctx.document:
            ctx.invoice = ctx.db.scalar(
                select(Invoice).where(Invoice.document_id == ctx.document.id)
            )
            ctx.purchase_order = ctx.db.scalar(
                select(PurchaseOrder).where(PurchaseOrder.document_id == ctx.document.id)
            )
    elif ctx.entity_type == "invoice" and entity_uuid:
        ctx.invoice = ctx.db.get(Invoice, entity_uuid)
        if ctx.invoice:
            ctx.document = ctx.db.get(Document, ctx.invoice.document_id)
    elif ctx.entity_type == "purchase_order" and entity_uuid:
        ctx.purchase_order = ctx.db.get(PurchaseOrder, entity_uuid)
        if ctx.purchase_order:
            ctx.document = ctx.db.get(Document, ctx.purchase_order.document_id)
    elif ctx.entity_type == "validation" and entity_uuid:
        ctx.validation = ctx.db.get(DocumentValidation, entity_uuid)
        if ctx.validation:
            ctx.validation_status = ctx.validation.status
            ctx.invoice = ctx.db.get(Invoice, ctx.validation.invoice_id)
            ctx.purchase_order = ctx.db.get(PurchaseOrder, ctx.validation.purchase_order_id)
            if ctx.invoice:
                ctx.document = ctx.db.get(Document, ctx.invoice.document_id)
    elif ctx.entity_type == "review" and entity_uuid:
        ctx.review = ctx.db.get(DocumentReview, entity_uuid)
        if ctx.review:
            ctx.document = ctx.db.get(Document, ctx.review.document_id)
            ctx.invoice = ctx.db.scalar(
                select(Invoice).where(Invoice.document_id == ctx.review.document_id)
            )
            ctx.purchase_order = ctx.db.scalar(
                select(PurchaseOrder).where(PurchaseOrder.document_id == ctx.review.document_id)
            )

    if ctx.invoice is not None:
        ctx.related_purchase_order = _find_related_purchase_order(ctx.db, ctx.invoice)


def _find_related_purchase_order(db: Session, invoice: Invoice) -> PurchaseOrder | None:
    if invoice.vendor_id is not None:
        match = db.scalar(
            select(PurchaseOrder)
            .where(PurchaseOrder.vendor_id == invoice.vendor_id)
            .order_by(PurchaseOrder.created_at.desc())
        )
        if match is not None:
            return match
    if invoice.vendor_name:
        normalized = invoice.vendor_name.strip().lower()
        candidates = db.scalars(
            select(PurchaseOrder).order_by(PurchaseOrder.created_at.desc())
        ).all()
        for po in candidates:
            if po.vendor_name and po.vendor_name.strip().lower() == normalized:
                return po
    return None


def evaluate_conditions(
    conditions: list[dict[str, Any]],
    ctx: WorkflowContext,
    *,
    mode: str = "all",
) -> tuple[bool, list[str]]:
    if not conditions:
        return True, ["No conditions configured; treated as satisfied."]

    results: list[tuple[bool, str]] = []
    for condition in conditions:
        ok, reason = evaluate_condition(condition, ctx)
        results.append((ok, reason))

    if mode == "any":
        passed = any(item[0] for item in results)
    else:
        passed = all(item[0] for item in results)

    return passed, [item[1] for item in results]


def evaluate_condition(condition: dict[str, Any], ctx: WorkflowContext) -> tuple[bool, str]:
    ctype = condition.get("type")
    if ctype == "all_of":
        ok, reasons = evaluate_conditions(
            list(condition.get("conditions") or []),
            ctx,
            mode="all",
        )
        return ok, f"all_of -> {ok}; " + "; ".join(reasons)
    if ctype == "any_of":
        ok, reasons = evaluate_conditions(
            list(condition.get("conditions") or []),
            ctx,
            mode="any",
        )
        return ok, f"any_of -> {ok}; " + "; ".join(reasons)

    if ctype == "has_invoice":
        ok = ctx.invoice is not None
        return ok, f"has_invoice={ok}"

    if ctype == "has_purchase_order":
        ok = ctx.purchase_order is not None
        return ok, f"has_purchase_order={ok}"

    if ctype == "has_related_purchase_order":
        ok = ctx.related_purchase_order is not None
        return ok, f"has_related_purchase_order={ok}"

    if ctype == "document_type_is":
        expected = condition.get("value") or condition.get("values")
        values = expected if isinstance(expected, list) else [expected]
        actual = ctx.document.document_type if ctx.document else None
        ok = actual in values
        return ok, f"document_type_is {values} actual={actual} -> {ok}"

    if ctype == "validation_status_is":
        values = condition.get("values") or [condition.get("value")]
        actual = ctx.validation_status or (ctx.validation.status if ctx.validation else None)
        ok = actual in values
        return ok, f"validation_status_is {values} actual={actual} -> {ok}"

    if ctype == "review_status_is":
        values = condition.get("values") or [condition.get("value")]
        actual = ctx.review.status if ctx.review else None
        ok = actual in values
        return ok, f"review_status_is {values} actual={actual} -> {ok}"

    if ctype == "classification_confidence_below":
        threshold = float(condition.get("threshold", settings.WORKFLOW_CONFIDENCE_THRESHOLD))
        confidence = ctx.document.classification_confidence if ctx.document else None
        ok = confidence is not None and confidence < threshold
        return ok, f"classification_confidence_below {threshold} actual={confidence} -> {ok}"

    if ctype == "extraction_confidence_below":
        threshold = float(condition.get("threshold", settings.WORKFLOW_CONFIDENCE_THRESHOLD))
        confidence = None
        if ctx.invoice is not None and ctx.invoice.extraction_confidence is not None:
            confidence = ctx.invoice.extraction_confidence
        elif ctx.purchase_order is not None and ctx.purchase_order.extraction_confidence is not None:
            confidence = ctx.purchase_order.extraction_confidence
        ok = confidence is not None and confidence < threshold
        return ok, f"extraction_confidence_below {threshold} actual={confidence} -> {ok}"

    if ctype == "has_required_invoice_fields":
        inv = ctx.invoice
        ok = bool(
            inv
            and inv.invoice_number
            and inv.vendor_name
            and inv.total_amount is not None
            and inv.currency
        )
        return ok, f"has_required_invoice_fields={ok}"

    if ctype == "has_required_po_fields":
        po = ctx.purchase_order or ctx.related_purchase_order
        ok = bool(po and po.po_number and po.vendor_name and po.total_amount is not None and po.currency)
        return ok, f"has_required_po_fields={ok}"

    return False, f"Unknown condition type: {ctype}"
