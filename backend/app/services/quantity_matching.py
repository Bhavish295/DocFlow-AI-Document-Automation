"""Quantity matching helpers for three-way Invoice ↔ PO ↔ GRN comparison."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re
from typing import Any

from app.core.config import settings
from app.models.document_line_item import DocumentLineItem
from app.models.validation import ValidationStatus


STATUS_MATCHED = ValidationStatus.MATCHED.value
STATUS_MISMATCH = ValidationStatus.MISMATCH.value
STATUS_NEEDS_REVIEW = ValidationStatus.NEEDS_REVIEW.value
STATUS_NOT_EVALUABLE = "not_evaluable"


@dataclass
class QuantityItemEvidence:
    item_key: str
    description: str | None
    item_code: str | None
    match_method: str | None
    po_quantity: float | None
    grn_quantity: float | None
    invoice_quantity: float | None
    status: str
    detail: str | None


def normalize_item_code(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"\s+", "", value.strip().upper())
    return cleaned or None


def normalize_description(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"[^\w\s]", " ", value.strip().lower())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or None


def description_tokens(value: str | None) -> frozenset[str]:
    normalized = normalize_description(value)
    if not normalized:
        return frozenset()
    return frozenset(token for token in normalized.split() if len(token) > 1)


def to_decimal(value) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def compare_quantity_constraint(
    lower: Decimal | None,
    upper: Decimal | None,
    *,
    tolerance: Decimal,
    lower_label: str,
    upper_label: str,
) -> tuple[str, str | None]:
    """Require lower <= upper within tolerance."""
    if lower is None or upper is None:
        missing = lower_label if lower is None else upper_label
        return STATUS_NEEDS_REVIEW, f"Missing {missing}"
    if lower <= upper + tolerance:
        return STATUS_MATCHED, None
    return (
        STATUS_MISMATCH,
        f"{lower_label} {float(lower)} exceeds {upper_label} {float(upper)}",
    )


def _float_qty(row: DocumentLineItem | None) -> float | None:
    if row is None or row.quantity is None:
        return None
    return float(row.quantity)


def _item_key(row: DocumentLineItem) -> str:
    code = normalize_item_code(row.item_code)
    if code:
        return code
    desc = normalize_description(row.description)
    if desc:
        return desc
    return f"line-{row.line_number}"


def _find_match_with_method(
    anchor: DocumentLineItem,
    candidates: list[DocumentLineItem],
    used: set[str],
) -> tuple[DocumentLineItem | None, str | None]:
    available = [row for row in candidates if str(row.id) not in used]
    if not available:
        return None, None

    anchor_code = normalize_item_code(anchor.item_code)
    if anchor_code:
        code_hits = [
            row for row in available if normalize_item_code(row.item_code) == anchor_code
        ]
        if len(code_hits) == 1:
            return code_hits[0], "sku"
        if len(code_hits) > 1:
            return None, "sku_ambiguous"

    anchor_desc = normalize_description(anchor.description)
    if anchor_desc:
        desc_hits = [
            row for row in available if normalize_description(row.description) == anchor_desc
        ]
        if len(desc_hits) == 1:
            return desc_hits[0], "description"
        if len(desc_hits) > 1:
            return None, "description_ambiguous"

    anchor_tokens = description_tokens(anchor.description)
    if anchor_tokens:
        token_hits = [
            row for row in available if description_tokens(row.description) == anchor_tokens
        ]
        if len(token_hits) == 1:
            return token_hits[0], "tokens"
        if len(token_hits) > 1:
            return None, "tokens_ambiguous"

    return None, None


def match_line_items(
    po_items: list[DocumentLineItem],
    grn_items: list[DocumentLineItem],
    invoice_items: list[DocumentLineItem],
) -> list[QuantityItemEvidence]:
    """Match items deterministically and evaluate quantity constraints."""
    tolerance = Decimal(str(settings.QUANTITY_MATCH_TOLERANCE))
    evidence: list[QuantityItemEvidence] = []
    if not po_items and not grn_items and not invoice_items:
        return evidence

    used_grn: set[str] = set()
    used_invoice: set[str] = set()
    anchors = po_items or grn_items or invoice_items

    for anchor in anchors:
        po_row = anchor if po_items and any(row.id == anchor.id for row in po_items) else None
        if po_row is None and po_items:
            po_row, _ = _find_match_with_method(anchor, po_items, set())

        grn_row, grn_method = _find_match_with_method(anchor, grn_items, used_grn)
        inv_row, inv_method = _find_match_with_method(anchor, invoice_items, used_invoice)
        if grn_row is not None:
            used_grn.add(str(grn_row.id))
        if inv_row is not None:
            used_invoice.add(str(inv_row.id))

        match_method = grn_method or inv_method or ("po_anchor" if po_row is not None else None)

        needs_partner = bool(po_items) and (bool(grn_items) or bool(invoice_items))
        if needs_partner and ((grn_items and grn_row is None) or (invoice_items and inv_row is None)):
            evidence.append(
                QuantityItemEvidence(
                    item_key=_item_key(anchor),
                    description=anchor.description,
                    item_code=anchor.item_code,
                    match_method=match_method,
                    po_quantity=_float_qty(po_row),
                    grn_quantity=_float_qty(grn_row),
                    invoice_quantity=_float_qty(inv_row),
                    status=STATUS_NEEDS_REVIEW,
                    detail="Line item could not be unambiguously matched across documents.",
                )
            )
            continue

        po_qty = to_decimal(po_row.quantity) if po_row else None
        grn_qty = to_decimal(grn_row.quantity) if grn_row else None
        inv_qty = to_decimal(inv_row.quantity) if inv_row else None

        statuses: list[str] = []
        details: list[str] = []
        if po_items and grn_items:
            status, detail = compare_quantity_constraint(
                grn_qty,
                po_qty,
                tolerance=tolerance,
                lower_label="GRN received",
                upper_label="PO ordered",
            )
            statuses.append(status)
            if detail:
                details.append(detail)
        if grn_items and invoice_items:
            status, detail = compare_quantity_constraint(
                inv_qty,
                grn_qty,
                tolerance=tolerance,
                lower_label="Invoice invoiced",
                upper_label="GRN received",
            )
            statuses.append(status)
            if detail:
                details.append(detail)

        if not statuses:
            item_status = STATUS_NEEDS_REVIEW
            detail_text = "Insufficient line-item sides present for quantity comparison."
        elif any(status == STATUS_MISMATCH for status in statuses):
            item_status = STATUS_MISMATCH
            detail_text = "; ".join(details) or "Quantity constraint violated."
        elif any(status == STATUS_NEEDS_REVIEW for status in statuses):
            item_status = STATUS_NEEDS_REVIEW
            detail_text = "; ".join(details) or "Quantity evidence incomplete."
        else:
            item_status = STATUS_MATCHED
            detail_text = "Quantities satisfy PO >= GRN >= Invoice within tolerance."

        source = po_row or grn_row or inv_row or anchor
        evidence.append(
            QuantityItemEvidence(
                item_key=_item_key(source),
                description=source.description,
                item_code=source.item_code,
                match_method=match_method,
                po_quantity=_float_qty(po_row),
                grn_quantity=_float_qty(grn_row),
                invoice_quantity=_float_qty(inv_row),
                status=item_status,
                detail=detail_text,
            )
        )

    for row in grn_items:
        if str(row.id) in used_grn:
            continue
        evidence.append(
            QuantityItemEvidence(
                item_key=_item_key(row),
                description=row.description,
                item_code=row.item_code,
                match_method=None,
                po_quantity=None,
                grn_quantity=_float_qty(row),
                invoice_quantity=None,
                status=STATUS_NEEDS_REVIEW,
                detail="GRN line item could not be matched to a corresponding PO line.",
            )
        )
    for row in invoice_items:
        if str(row.id) in used_invoice:
            continue
        evidence.append(
            QuantityItemEvidence(
                item_key=_item_key(row),
                description=row.description,
                item_code=row.item_code,
                match_method=None,
                po_quantity=None,
                grn_quantity=None,
                invoice_quantity=_float_qty(row),
                status=STATUS_NEEDS_REVIEW,
                detail="Invoice line item could not be matched to a corresponding partner line.",
            )
        )

    return evidence


def summarize_quantity_evidence(
    evidence: list[QuantityItemEvidence],
) -> tuple[str, str, list[dict[str, Any]], str | None, str | None, str | None]:
    if not evidence:
        detail = (
            "Quantity matching is not evaluable because no line items were extracted "
            "for the invoice, purchase order, and/or goods receipt."
        )
        return (
            STATUS_NOT_EVALUABLE,
            detail,
            [],
            None,
            None,
            "Quantity matching: line-item quantities unavailable",
        )

    payload = [
        {
            "item_key": item.item_key,
            "description": item.description,
            "item_code": item.item_code,
            "match_method": item.match_method,
            "po_quantity": item.po_quantity,
            "grn_quantity": item.grn_quantity,
            "invoice_quantity": item.invoice_quantity,
            "status": item.status,
            "detail": item.detail,
        }
        for item in evidence
    ]

    if any(item.status == STATUS_MISMATCH for item in evidence):
        detail = "Quantity mismatch on one or more line items. " + "; ".join(
            item.detail for item in evidence if item.status == STATUS_MISMATCH and item.detail
        )
        return STATUS_MISMATCH, detail, payload, None, "Quantity: mismatch", None

    if any(item.status in {STATUS_NEEDS_REVIEW, STATUS_NOT_EVALUABLE} for item in evidence):
        detail = "Quantity needs review. " + "; ".join(
            item.detail
            for item in evidence
            if item.status in {STATUS_NEEDS_REVIEW, STATUS_NOT_EVALUABLE} and item.detail
        )
        return STATUS_NEEDS_REVIEW, detail, payload, None, None, "Quantity: needs review"

    detail = "Quantity matched for all unambiguously linked line items."
    return STATUS_MATCHED, detail, payload, "Quantity: matched", None, None
