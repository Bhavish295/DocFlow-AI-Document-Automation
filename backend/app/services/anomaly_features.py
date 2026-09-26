"""Feature engineering for invoice anomaly detection.

Historical vendor statistics for an invoice use only earlier invoices
(by created_at, then id) to avoid future-data leakage when scoring.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.invoice import Invoice


FEATURE_NAMES: tuple[str, ...] = (
    "total_amount",
    "subtotal",
    "tax_amount",
    "tax_ratio",
    "vendor_avg_ratio",
    "vendor_median_ratio",
    "vendor_historical_count",
    "vendor_amount_deviation",
    "has_invoice_number",
    "invoice_number_digit_count",
    "extraction_confidence",
)


@dataclass(frozen=True)
class InvoiceFeatureRow:
    invoice_id: UUID
    document_id: UUID
    vendor_key: str
    vendor_name: str | None
    features: dict[str, float]
    vector: list[float]
    raw_values: dict[str, Any]


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe(value: float | None, default: float = 0.0) -> float:
    if value is None:
        return default
    if value != value:  # NaN
        return default
    return float(value)


def _vendor_key(invoice: Invoice) -> str:
    if invoice.vendor_id is not None:
        return f"id:{invoice.vendor_id}"
    if invoice.vendor_name and invoice.vendor_name.strip():
        return f"name:{invoice.vendor_name.strip().lower()}"
    return "unknown"


def _digit_count(invoice_number: str | None) -> int:
    if not invoice_number:
        return 0
    return sum(1 for ch in invoice_number if ch.isdigit())


def _historical_amounts(history: list[Invoice]) -> list[float]:
    amounts: list[float] = []
    for item in history:
        total = _to_float(item.total_amount)
        if total is not None:
            amounts.append(total)
    return amounts


def build_feature_row(invoice: Invoice, history: list[Invoice]) -> InvoiceFeatureRow | None:
    """Build features for one invoice using only prior invoices as history."""
    total = _to_float(invoice.total_amount)
    if total is None:
        return None

    subtotal = _to_float(invoice.subtotal)
    tax = _to_float(invoice.tax_amount)
    confidence = _to_float(invoice.extraction_confidence)

    if subtotal is not None and subtotal > 0 and tax is not None:
        tax_ratio = tax / subtotal
    else:
        tax_ratio = 0.0

    amounts = _historical_amounts(history)
    hist_count = float(len(amounts))
    if amounts:
        avg = sum(amounts) / len(amounts)
        med = float(median(amounts))
        vendor_avg_ratio = total / avg if avg else 1.0
        vendor_median_ratio = total / med if med else 1.0
        if len(amounts) >= 2:
            mean = avg
            variance = sum((a - mean) ** 2 for a in amounts) / len(amounts)
            std = variance**0.5
            vendor_amount_deviation = abs(total - mean) / std if std > 0 else 0.0
        else:
            vendor_amount_deviation = abs(total - avg) / avg if avg else 0.0
    else:
        vendor_avg_ratio = 1.0
        vendor_median_ratio = 1.0
        vendor_amount_deviation = 0.0

    features = {
        "total_amount": _safe(total),
        "subtotal": _safe(subtotal),
        "tax_amount": _safe(tax),
        "tax_ratio": _safe(tax_ratio),
        "vendor_avg_ratio": _safe(vendor_avg_ratio, 1.0),
        "vendor_median_ratio": _safe(vendor_median_ratio, 1.0),
        "vendor_historical_count": hist_count,
        "vendor_amount_deviation": _safe(vendor_amount_deviation),
        "has_invoice_number": 1.0 if invoice.invoice_number else 0.0,
        "invoice_number_digit_count": float(_digit_count(invoice.invoice_number)),
        "extraction_confidence": _safe(confidence),
    }
    vector = [features[name] for name in FEATURE_NAMES]
    return InvoiceFeatureRow(
        invoice_id=invoice.id,
        document_id=invoice.document_id,
        vendor_key=_vendor_key(invoice),
        vendor_name=invoice.vendor_name,
        features=features,
        vector=vector,
        raw_values={
            "total_amount": total,
            "subtotal": subtotal,
            "tax_amount": tax,
            "extraction_confidence": confidence,
            "invoice_number": invoice.invoice_number,
            "historical_sample_count": len(amounts),
            "historical_avg": (sum(amounts) / len(amounts)) if amounts else None,
            "historical_median": float(median(amounts)) if amounts else None,
        },
    )


def load_invoices_chronological(db: Session) -> list[Invoice]:
    return list(
        db.scalars(
            select(Invoice).order_by(Invoice.created_at.asc(), Invoice.id.asc())
        ).all()
    )


def build_feature_matrix(db: Session) -> list[InvoiceFeatureRow]:
    """Build leakage-safe feature rows for all invoices with a total amount."""
    invoices = load_invoices_chronological(db)
    by_vendor: dict[str, list[Invoice]] = {}
    rows: list[InvoiceFeatureRow] = []
    for invoice in invoices:
        key = _vendor_key(invoice)
        history = by_vendor.get(key, [])
        row = build_feature_row(invoice, history)
        if row is not None:
            rows.append(row)
        by_vendor.setdefault(key, []).append(invoice)
    return rows


def build_feature_row_for_invoice(db: Session, invoice: Invoice) -> InvoiceFeatureRow | None:
    """Score-time features using only invoices created before this invoice."""
    invoices = load_invoices_chronological(db)
    history: list[Invoice] = []
    for item in invoices:
        if item.id == invoice.id:
            break
        if _vendor_key(item) == _vendor_key(invoice):
            history.append(item)
    return build_feature_row(invoice, history)


def explain_feature_deviations(row: InvoiceFeatureRow) -> list[str]:
    """Deterministic human-readable reasons from actual feature values."""
    reasons: list[str] = []
    raw = row.raw_values
    features = row.features

    hist_median = raw.get("historical_median")
    total = raw.get("total_amount")
    if (
        hist_median is not None
        and total is not None
        and hist_median > 0
        and features["vendor_median_ratio"] >= 2.0
    ):
        reasons.append(
            "Invoice total is significantly higher than this vendor's historical median."
        )
    elif (
        hist_median is not None
        and total is not None
        and hist_median > 0
        and features["vendor_median_ratio"] <= 0.5
        and features["vendor_historical_count"] >= 2
    ):
        reasons.append(
            "Invoice total is significantly lower than this vendor's historical median."
        )

    if features["vendor_amount_deviation"] >= 2.5 and features["vendor_historical_count"] >= 2:
        reasons.append(
            "Invoice amount deviation from this vendor's historical distribution is high."
        )

    if features["tax_ratio"] >= 0.35:
        reasons.append("Tax ratio relative to subtotal is unusually high.")
    elif features["tax_amount"] > 0 and features["subtotal"] == 0:
        reasons.append("Tax amount is present while subtotal is missing or zero.")

    if features["vendor_historical_count"] == 0:
        reasons.append(
            "Little or no prior vendor history was available; score relies more on absolute amounts."
        )

    if features["has_invoice_number"] == 0.0:
        reasons.append("Invoice number is missing.")

    if features["extraction_confidence"] > 0 and features["extraction_confidence"] < 0.5:
        reasons.append("Extraction confidence for this invoice is low.")

    if not reasons:
        if features["vendor_avg_ratio"] >= 1.5:
            reasons.append("Invoice total is above this vendor's historical average.")
        else:
            reasons.append(
                "Feature values are within typical ranges relative to available historical data."
            )
    return reasons
