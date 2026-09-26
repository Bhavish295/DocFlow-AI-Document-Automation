"""Tests for anomaly feature engineering."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.anomaly_features import (
    FEATURE_NAMES,
    build_feature_row,
    explain_feature_deviations,
)


def _invoice(**kwargs):
    defaults = {
        "id": uuid.uuid4(),
        "document_id": uuid.uuid4(),
        "vendor_id": None,
        "vendor_name": "Acme",
        "invoice_number": "INV-1",
        "subtotal": 100,
        "tax_amount": 10,
        "total_amount": 110,
        "extraction_confidence": 0.9,
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_feature_extraction_basic():
    history = [
        _invoice(total_amount=100, vendor_name="Acme"),
        _invoice(total_amount=120, vendor_name="Acme"),
    ]
    current = _invoice(total_amount=500, vendor_name="Acme", tax_amount=50, subtotal=450)
    row = build_feature_row(current, history)
    assert row is not None
    assert list(row.features.keys()) == list(FEATURE_NAMES)
    assert len(row.vector) == len(FEATURE_NAMES)
    assert row.features["total_amount"] == 500
    assert row.features["vendor_historical_count"] == 2
    assert row.features["vendor_median_ratio"] > 1


def test_missing_total_returns_none():
    row = build_feature_row(_invoice(total_amount=None), [])
    assert row is None


def test_missing_optional_values_safe():
    row = build_feature_row(
        _invoice(
            subtotal=None,
            tax_amount=None,
            invoice_number=None,
            extraction_confidence=None,
            total_amount=50,
        ),
        [],
    )
    assert row is not None
    assert row.features["subtotal"] == 0.0
    assert row.features["has_invoice_number"] == 0.0
    assert row.features["vendor_historical_count"] == 0


def test_explanation_high_median_ratio():
    history = [_invoice(total_amount=100), _invoice(total_amount=110)]
    row = build_feature_row(_invoice(total_amount=400), history)
    assert row is not None
    reasons = explain_feature_deviations(row)
    assert any("historical median" in reason.lower() for reason in reasons)
    assert all("fraud" not in reason.lower() for reason in reasons)
