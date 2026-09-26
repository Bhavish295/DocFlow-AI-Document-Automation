"""Tests for workflow condition evaluation."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.workflow_conditions import WorkflowContext, evaluate_condition, evaluate_conditions


def _ctx(**kwargs) -> WorkflowContext:
    defaults = {
        "db": SimpleNamespace(),
        "trigger_event": "document_processed",
        "entity_type": "document",
        "entity_id": str(uuid.uuid4()),
    }
    defaults.update(kwargs)
    return WorkflowContext(**defaults)


def test_has_invoice_condition():
    ok, _ = evaluate_condition({"type": "has_invoice"}, _ctx(invoice=object()))
    assert ok is True
    ok, _ = evaluate_condition({"type": "has_invoice"}, _ctx(invoice=None))
    assert ok is False


def test_classification_confidence_below():
    document = SimpleNamespace(classification_confidence=0.4, document_type="invoice")
    ok, _ = evaluate_condition(
        {"type": "classification_confidence_below", "threshold": 0.7},
        _ctx(document=document),
    )
    assert ok is True

    document.classification_confidence = 0.9
    ok, _ = evaluate_condition(
        {"type": "classification_confidence_below", "threshold": 0.7},
        _ctx(document=document),
    )
    assert ok is False


def test_condition_mode_any():
    document = SimpleNamespace(classification_confidence=0.9, document_type="invoice")
    invoice = SimpleNamespace(extraction_confidence=0.2)
    passed, notes = evaluate_conditions(
        [
            {"type": "classification_confidence_below", "threshold": 0.7},
            {"type": "extraction_confidence_below", "threshold": 0.7},
        ],
        _ctx(document=document, invoice=invoice),
        mode="any",
    )
    assert passed is True
    assert notes


def test_review_status_condition():
    review = SimpleNamespace(status="approved", created_at=datetime.now(timezone.utc))
    ok, _ = evaluate_condition(
        {"type": "review_status_is", "values": ["approved", "rejected"]},
        _ctx(review=review),
    )
    assert ok is True
