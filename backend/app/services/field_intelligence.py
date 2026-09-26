"""Deterministic field checks for stored invoice and purchase order values."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppError
from app.models.document import Document, DocumentType
from app.models.goods_receipt import GoodsReceipt
from app.models.invoice import Invoice
from app.models.purchase_order import PurchaseOrder
from app.schemas.field_intelligence import FieldIntelligenceField, FieldIntelligenceResponse
from app.services.invoice_extraction import parse_date

STATUS_VALID = "valid"
STATUS_MISSING = "missing"
STATUS_SUSPICIOUS = "suspicious"
STATUS_INVALID = "invalid"

OVERALL_VALID = "valid"
OVERALL_NEEDS_REVIEW = "needs_review"
OVERALL_UNAVAILABLE = "unavailable"

ISSUE_MISSING = "missing"
ISSUE_NEGATIVE_AMOUNT = "negative_amount"
ISSUE_MALFORMED_AMOUNT = "malformed_amount"
ISSUE_INVALID_DATE = "invalid_date"
ISSUE_UNEXPECTED_CURRENCY = "unexpected_currency"
ISSUE_INVALID_CURRENCY = "invalid_currency"
ISSUE_FINANCIAL_MISMATCH = "subtotal_tax_total_mismatch"
ISSUE_LOW_EXTRACTION = "low_extraction_confidence"
ISSUE_EXTRACTION_DATA_MISSING = "extraction_data_missing"
ISSUE_NEGATIVE_QUANTITY = "negative_quantity"
ISSUE_MALFORMED_QUANTITY = "malformed_quantity"

INVOICE_FIELDS = (
    "invoice_number",
    "invoice_date",
    "vendor_name",
    "subtotal",
    "tax_amount",
    "total_amount",
    "currency",
)
PURCHASE_ORDER_FIELDS = (
    "po_number",
    "po_date",
    "vendor_name",
    "subtotal",
    "tax_amount",
    "total_amount",
    "currency",
)
GOODS_RECEIPT_FIELDS = (
    "grn_number",
    "grn_date",
    "vendor_name",
    "po_number",
    "total_received_quantity",
)
DATE_FIELDS = {"invoice_date", "po_date", "grn_date"}
NUMBER_FIELDS = {"invoice_number", "po_number", "grn_number"}
AMOUNT_FIELDS = {"subtotal", "tax_amount", "total_amount"}
QUANTITY_FIELDS = {"total_received_quantity"}
FINANCIAL_FIELDS = ("subtotal", "tax_amount", "total_amount")

# Matches the review queue extraction-confidence threshold.
EXTRACTION_CONFIDENCE_THRESHOLD = 0.70
CONFIDENCE_VALID = 1.0
CONFIDENCE_SUSPICIOUS = 0.55
CONFIDENCE_MISMATCH = 0.45
CONFIDENCE_INVALID = 0.2
CONFIDENCE_MISSING = 0.0

KNOWN_CURRENCY_CODES = {"PKR", "USD", "EUR", "GBP"}
CURRENCY_ALIASES = {
    "pkr": "PKR",
    "rs": "PKR",
    "rs.": "PKR",
    "usd": "USD",
    "$": "USD",
    "eur": "EUR",
    "€": "EUR",
    "gbp": "GBP",
    "£": "GBP",
}
CURRENCY_CODE_PATTERN = re.compile(r"^[A-Za-z]{3}$")


@dataclass
class FieldCheck:
    field_name: str
    value: float | str | None
    status: str
    confidence: float
    issues: list[str] = field(default_factory=list)


@dataclass
class FieldIntelligenceResult:
    document_type: str
    overall_status: str
    overall_confidence: float
    fields: list[FieldCheck]
    issues: list[str]
    review_required: bool
    extraction_confidence: float | None = None


def evaluate_invoice_fields(
    values: dict,
    extraction_confidence: float | None = None,
) -> FieldIntelligenceResult:
    return _evaluate(DocumentType.INVOICE.value, INVOICE_FIELDS, values, extraction_confidence)


def evaluate_purchase_order_fields(
    values: dict,
    extraction_confidence: float | None = None,
) -> FieldIntelligenceResult:
    return _evaluate(
        DocumentType.PURCHASE_ORDER.value,
        PURCHASE_ORDER_FIELDS,
        values,
        extraction_confidence,
    )


def evaluate_invoice_model(invoice: Invoice) -> FieldIntelligenceResult:
    values = {name: getattr(invoice, name) for name in INVOICE_FIELDS}
    return evaluate_invoice_fields(values, invoice.extraction_confidence)


def evaluate_purchase_order_model(purchase_order: PurchaseOrder) -> FieldIntelligenceResult:
    values = {name: getattr(purchase_order, name) for name in PURCHASE_ORDER_FIELDS}
    return evaluate_purchase_order_fields(values, purchase_order.extraction_confidence)


def evaluate_goods_receipt_fields(
    values: dict,
    extraction_confidence: float | None = None,
) -> FieldIntelligenceResult:
    return _evaluate(
        DocumentType.GOODS_RECEIPT.value,
        GOODS_RECEIPT_FIELDS,
        values,
        extraction_confidence,
        apply_financial=False,
    )


def evaluate_goods_receipt_model(goods_receipt: GoodsReceipt) -> FieldIntelligenceResult:
    values = {name: getattr(goods_receipt, name) for name in GOODS_RECEIPT_FIELDS}
    return evaluate_goods_receipt_fields(values, goods_receipt.extraction_confidence)


def review_request_for_result(result: FieldIntelligenceResult) -> tuple[str, str, str] | None:
    """Return reason, priority, and details when a human review should be opened."""
    if not result.review_required:
        return None

    from app.models.document_review import ReviewPriority, ReviewReason

    statuses = {item.status for item in result.fields}
    if STATUS_INVALID in statuses:
        reason = ReviewReason.FIELD_INVALID.value
        priority = ReviewPriority.HIGH.value
    elif ISSUE_FINANCIAL_MISMATCH in result.issues:
        reason = ReviewReason.FINANCIAL_CONSISTENCY_MISMATCH.value
        priority = ReviewPriority.HIGH.value
    elif STATUS_SUSPICIOUS in statuses:
        reason = ReviewReason.FIELD_SUSPICIOUS.value
        priority = ReviewPriority.MEDIUM.value
    elif STATUS_MISSING in statuses:
        reason = ReviewReason.FIELD_MISSING.value
        priority = ReviewPriority.MEDIUM.value
    elif ISSUE_LOW_EXTRACTION in result.issues:
        reason = ReviewReason.LOW_EXTRACTION_CONFIDENCE.value
        priority = ReviewPriority.MEDIUM.value
    else:
        return None

    flagged = [
        f"{item.field_name} ({item.status})"
        for item in result.fields
        if item.status != STATUS_VALID
    ]
    details = "Field intelligence found actionable issues: " + ", ".join(result.issues)
    if flagged:
        details += ". Fields: " + ", ".join(flagged)
    details += "."
    return reason, priority, details


def unavailable_response(
    document_id: uuid.UUID,
    document_type: str | None,
) -> FieldIntelligenceResponse:
    return FieldIntelligenceResponse(
        document_id=document_id,
        document_type=document_type,
        overall_status=OVERALL_UNAVAILABLE,
        overall_confidence=0.0,
        fields=[],
        issues=[ISSUE_EXTRACTION_DATA_MISSING],
        review_required=False,
    )


class FieldIntelligenceService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_for_document(self, document_id: uuid.UUID) -> FieldIntelligenceResponse:
        document = self.db.get(Document, document_id)
        if document is None:
            raise AppError("Document not found.", status_code=404)

        if document.document_type == DocumentType.INVOICE.value:
            invoice = self.db.scalar(select(Invoice).where(Invoice.document_id == document.id))
            if invoice is None:
                return unavailable_response(document.id, document.document_type)
            return _to_response(document.id, evaluate_invoice_model(invoice))

        if document.document_type == DocumentType.PURCHASE_ORDER.value:
            purchase_order = self.db.scalar(
                select(PurchaseOrder).where(PurchaseOrder.document_id == document.id)
            )
            if purchase_order is None:
                return unavailable_response(document.id, document.document_type)
            return _to_response(document.id, evaluate_purchase_order_model(purchase_order))

        if document.document_type == DocumentType.GOODS_RECEIPT.value:
            goods_receipt = self.db.scalar(
                select(GoodsReceipt).where(GoodsReceipt.document_id == document.id)
            )
            if goods_receipt is None:
                return unavailable_response(document.id, document.document_type)
            return _to_response(document.id, evaluate_goods_receipt_model(goods_receipt))

        return unavailable_response(document.id, document.document_type)


def _evaluate(
    document_type: str,
    field_names: tuple[str, ...],
    values: dict,
    extraction_confidence: float | None,
    *,
    apply_financial: bool = True,
) -> FieldIntelligenceResult:
    checks = [_check_field(name, values.get(name)) for name in field_names]
    issues: list[str] = []

    if any(item.status == STATUS_MISSING for item in checks):
        issues.append("field_missing")

    if apply_financial:
        _apply_financial_consistency(checks, issues)

    for item in checks:
        if item.status == STATUS_INVALID and "field_invalid" not in issues:
            issues.append("field_invalid")
        if item.status == STATUS_SUSPICIOUS and "field_suspicious" not in issues:
            issues.append("field_suspicious")

    if extraction_confidence is not None and extraction_confidence < EXTRACTION_CONFIDENCE_THRESHOLD:
        issues.append(ISSUE_LOW_EXTRACTION)
        for item in checks:
            item.confidence = _clamp(item.confidence * float(extraction_confidence))

    review_required = bool(issues)
    if review_required:
        overall_status = OVERALL_NEEDS_REVIEW
    else:
        overall_status = OVERALL_VALID

    overall = 0.0
    if checks:
        overall = _clamp(sum(item.confidence for item in checks) / len(checks))

    return FieldIntelligenceResult(
        document_type=document_type,
        overall_status=overall_status,
        overall_confidence=overall,
        fields=checks,
        issues=issues,
        review_required=review_required,
        extraction_confidence=extraction_confidence,
    )


def _check_field(name: str, raw) -> FieldCheck:
    if name in DATE_FIELDS:
        return _check_date(name, raw)
    if name in AMOUNT_FIELDS:
        return _check_amount(name, raw)
    if name in QUANTITY_FIELDS:
        return _check_quantity(name, raw)
    if name == "currency":
        return _check_currency(raw)
    if name in NUMBER_FIELDS or name == "vendor_name":
        return _check_text(name, raw)
    return _check_text(name, raw)


def _check_text(name: str, raw) -> FieldCheck:
    if _is_blank(raw):
        return FieldCheck(name, _display_value(raw), STATUS_MISSING, CONFIDENCE_MISSING, [ISSUE_MISSING])
    return FieldCheck(name, _display_value(raw), STATUS_VALID, CONFIDENCE_VALID, [])


def _check_date(name: str, raw) -> FieldCheck:
    if _is_blank(raw):
        return FieldCheck(name, None, STATUS_MISSING, CONFIDENCE_MISSING, [ISSUE_MISSING])
    if isinstance(raw, datetime):
        return FieldCheck(name, raw.date().isoformat(), STATUS_VALID, CONFIDENCE_VALID, [])
    if isinstance(raw, date):
        return FieldCheck(name, raw.isoformat(), STATUS_VALID, CONFIDENCE_VALID, [])
    if isinstance(raw, str) and parse_date(raw) is not None:
        return FieldCheck(name, raw, STATUS_VALID, CONFIDENCE_VALID, [])
    return FieldCheck(
        name,
        _display_value(raw),
        STATUS_INVALID,
        CONFIDENCE_INVALID,
        [ISSUE_INVALID_DATE],
    )


def _check_amount(name: str, raw) -> FieldCheck:
    if _is_blank(raw):
        return FieldCheck(name, None, STATUS_MISSING, CONFIDENCE_MISSING, [ISSUE_MISSING])

    parsed = _parse_amount(raw)
    if parsed is None:
        return FieldCheck(
            name,
            _display_value(raw),
            STATUS_INVALID,
            CONFIDENCE_INVALID,
            [ISSUE_MALFORMED_AMOUNT],
        )
    if parsed < 0:
        return FieldCheck(
            name,
            float(parsed),
            STATUS_INVALID,
            CONFIDENCE_INVALID,
            [ISSUE_NEGATIVE_AMOUNT],
        )
    return FieldCheck(name, float(parsed), STATUS_VALID, CONFIDENCE_VALID, [])


def _check_quantity(name: str, raw) -> FieldCheck:
    if _is_blank(raw):
        return FieldCheck(name, None, STATUS_MISSING, CONFIDENCE_MISSING, [ISSUE_MISSING])

    parsed = _parse_amount(raw)
    if parsed is None:
        return FieldCheck(
            name,
            _display_value(raw),
            STATUS_INVALID,
            CONFIDENCE_INVALID,
            [ISSUE_MALFORMED_QUANTITY],
        )
    if parsed < 0:
        return FieldCheck(
            name,
            float(parsed),
            STATUS_INVALID,
            CONFIDENCE_INVALID,
            [ISSUE_NEGATIVE_QUANTITY],
        )
    return FieldCheck(name, float(parsed), STATUS_VALID, CONFIDENCE_VALID, [])


def _check_currency(raw) -> FieldCheck:
    if _is_blank(raw):
        return FieldCheck("currency", _display_value(raw) if raw is not None else None, STATUS_MISSING, CONFIDENCE_MISSING, [ISSUE_MISSING])

    original = raw if isinstance(raw, str) else str(raw)
    token = original.strip()
    normalized = CURRENCY_ALIASES.get(token.lower())
    if normalized in KNOWN_CURRENCY_CODES:
        return FieldCheck("currency", original, STATUS_VALID, CONFIDENCE_VALID, [])
    if CURRENCY_CODE_PATTERN.fullmatch(token):
        return FieldCheck(
            "currency",
            original,
            STATUS_SUSPICIOUS,
            CONFIDENCE_SUSPICIOUS,
            [ISSUE_UNEXPECTED_CURRENCY],
        )
    return FieldCheck(
        "currency",
        original,
        STATUS_INVALID,
        CONFIDENCE_INVALID,
        [ISSUE_INVALID_CURRENCY],
    )


def _apply_financial_consistency(checks: list[FieldCheck], issues: list[str]) -> None:
    by_name = {item.field_name: item for item in checks}
    amounts: dict[str, Decimal] = {}
    for name in FINANCIAL_FIELDS:
        item = by_name.get(name)
        if item is None or item.status != STATUS_VALID or item.value is None:
            return
        parsed = _parse_amount(item.value)
        if parsed is None or parsed < 0:
            return
        amounts[name] = parsed

    tolerance = Decimal(str(settings.VALIDATION_AMOUNT_TOLERANCE))
    difference = abs((amounts["subtotal"] + amounts["tax_amount"]) - amounts["total_amount"])
    if difference <= tolerance:
        return

    issues.append(ISSUE_FINANCIAL_MISMATCH)
    for name in FINANCIAL_FIELDS:
        item = by_name[name]
        item.status = STATUS_SUSPICIOUS
        item.confidence = CONFIDENCE_MISMATCH
        if ISSUE_FINANCIAL_MISMATCH not in item.issues:
            item.issues.append(ISSUE_FINANCIAL_MISMATCH)


def _parse_amount(raw) -> Decimal | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, Decimal):
        return raw
    if isinstance(raw, (int, float)):
        if isinstance(raw, float) and raw != raw:
            return None
        try:
            return Decimal(str(raw))
        except InvalidOperation:
            return None
    if isinstance(raw, str):
        cleaned = raw.strip().replace(",", "")
        if not cleaned:
            return None
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return None
    return None


def _is_blank(raw) -> bool:
    if raw is None:
        return True
    if isinstance(raw, str) and not raw.strip():
        return True
    return False


def _display_value(raw) -> float | str | None:
    if raw is None:
        return None
    if isinstance(raw, Decimal):
        return float(raw)
    if isinstance(raw, float):
        return raw
    if isinstance(raw, int) and not isinstance(raw, bool):
        return float(raw)
    if isinstance(raw, date):
        return raw.isoformat()
    return str(raw)


def _clamp(value: float) -> float:
    return round(min(1.0, max(0.0, value)), 4)


def _to_response(document_id: uuid.UUID, result: FieldIntelligenceResult) -> FieldIntelligenceResponse:
    return FieldIntelligenceResponse(
        document_id=document_id,
        document_type=result.document_type,
        overall_status=result.overall_status,
        overall_confidence=result.overall_confidence,
        fields=[
            FieldIntelligenceField(
                field_name=item.field_name,
                value=item.value,
                status=item.status,
                confidence=item.confidence,
                issues=list(item.issues),
            )
            for item in result.fields
        ],
        issues=list(result.issues),
        review_required=result.review_required,
    )
