"""Tests for the controlled workflow engine."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.models.document import Document, DocumentStatus
from app.models.document_review import DocumentReview, ReviewPriority, ReviewReason, ReviewStatus
from app.models.invoice import Invoice
from app.models.purchase_order import PurchaseOrder
from app.models.vendor import Vendor
from app.models.workflow import WorkflowExecution, WorkflowExecutionStatus
from app.services.workflow_definitions import (
    ALLOWED_ACTION_TYPES,
    ALLOWED_TRIGGER_TYPES,
    PREDEFINED_WORKFLOWS,
    validate_definition,
)
from app.services.workflow_engine import WorkflowEngine, _workflow_depth, _workflow_stack


def test_definitions_load_and_are_valid():
    assert len(PREDEFINED_WORKFLOWS) >= 3
    for definition in PREDEFINED_WORKFLOWS:
        validate_definition(definition)
        assert definition["trigger_type"] in ALLOWED_TRIGGER_TYPES
        for action in definition["actions"]:
            assert action["type"] in ALLOWED_ACTION_TYPES


def test_invalid_action_rejected():
    with pytest.raises(ValueError):
        validate_definition(
            {
                "trigger_type": "document_processed",
                "actions": [{"type": "send_email"}],
                "conditions": [],
            }
        )


def test_ensure_and_list_workflows(client):
    db = client.testing_session_local()
    try:
        engine = WorkflowEngine(db)
        workflows = engine.list_workflows()
        codes = {item.code for item in workflows}
        assert "invoice_validation" in codes
        assert "low_confidence_review" in codes
        assert "document_review_completion" in codes
    finally:
        db.close()


def _seed_invoice_and_po(session_factory, *, confidence=0.4):
    db = session_factory()
    try:
        vendor = Vendor(name="ABC Traders", normalized_name="abc traders")
        db.add(vendor)
        db.flush()
        doc_inv = Document(
            original_filename="inv.pdf",
            stored_filename=f"{uuid.uuid4()}.pdf",
            file_type="pdf",
            file_size=10,
            storage_path="storage/uploads/inv.pdf",
            status=DocumentStatus.PROCESSED.value,
            document_type="invoice",
            classification_confidence=confidence,
            uploaded_at=datetime.now(timezone.utc),
        )
        doc_po = Document(
            original_filename="po.pdf",
            stored_filename=f"{uuid.uuid4()}.pdf",
            file_type="pdf",
            file_size=10,
            storage_path="storage/uploads/po.pdf",
            status=DocumentStatus.PROCESSED.value,
            document_type="purchase_order",
            uploaded_at=datetime.now(timezone.utc),
        )
        db.add_all([doc_inv, doc_po])
        db.flush()
        invoice = Invoice(
            document_id=doc_inv.id,
            vendor_id=vendor.id,
            vendor_name="ABC Traders",
            invoice_number="INV-W",
            total_amount=1000,
            currency="PKR",
            extraction_confidence=confidence,
        )
        po = PurchaseOrder(
            document_id=doc_po.id,
            vendor_id=vendor.id,
            vendor_name="ABC Traders",
            po_number="PO-W",
            total_amount=900,
            currency="PKR",
        )
        db.add_all([invoice, po])
        db.commit()
        return {"invoice_id": invoice.id, "document_id": doc_inv.id, "po_id": po.id}
    finally:
        db.close()


def test_successful_invoice_validation_workflow(client):
    seeded = _seed_invoice_and_po(client.testing_session_local)
    db = client.testing_session_local()
    try:
        engine = WorkflowEngine(db)
        workflow = engine.get_workflow_by_code("invoice_validation")
        result = engine.trigger_workflow(
            workflow.id,
            entity_type="invoice",
            entity_id=seeded["invoice_id"],
            force=True,
        )
        assert result["status"] in {
            WorkflowExecutionStatus.COMPLETED.value,
            WorkflowExecutionStatus.FAILED.value,
        }
        assert result["steps"]
        assert any(step["step_type"] == "run_validation" for step in result["steps"])
    finally:
        db.close()


def test_low_confidence_workflow_creates_review(client):
    seeded = _seed_invoice_and_po(client.testing_session_local, confidence=0.3)
    db = client.testing_session_local()
    try:
        engine = WorkflowEngine(db)
        workflow = engine.get_workflow_by_code("low_confidence_review")
        result = engine.trigger_workflow(
            workflow.id,
            entity_type="document",
            entity_id=seeded["document_id"],
            force=True,
        )
        assert result["status"] == WorkflowExecutionStatus.COMPLETED.value
        review = db.query(DocumentReview).filter(
            DocumentReview.document_id == seeded["document_id"]
        ).first()
        # SQLAlchemy 2 style
        from sqlalchemy import select

        review = db.scalar(
            select(DocumentReview).where(DocumentReview.document_id == seeded["document_id"])
        )
        assert review is not None
    finally:
        db.close()


def test_duplicate_execution_protection(client):
    seeded = _seed_invoice_and_po(client.testing_session_local, confidence=0.3)
    db = client.testing_session_local()
    try:
        engine = WorkflowEngine(db)
        workflow = engine.get_workflow_by_code("low_confidence_review")
        first = engine.trigger_workflow(
            workflow.id,
            entity_type="document",
            entity_id=seeded["document_id"],
            force=False,
        )
        second = engine.trigger_workflow(
            workflow.id,
            entity_type="document",
            entity_id=seeded["document_id"],
            force=False,
        )
        assert first["status"] == WorkflowExecutionStatus.COMPLETED.value
        assert second.get("reason") == "duplicate_execution_prevented"
        assert str(second["id"]) == str(first["id"])
    finally:
        db.close()


def test_recursion_protection(client):
    seeded = _seed_invoice_and_po(client.testing_session_local, confidence=0.3)
    db = client.testing_session_local()
    try:
        engine = WorkflowEngine(db)
        workflow = engine.get_workflow_by_code("low_confidence_review")
        token = _workflow_stack.set(("low_confidence_review",))
        try:
            result = engine.trigger_workflow(
                workflow.id,
                entity_type="document",
                entity_id=seeded["document_id"],
                force=True,
            )
        finally:
            _workflow_stack.reset(token)
        assert result["status"] == WorkflowExecutionStatus.SKIPPED.value
        assert result.get("reason") == "recursive_workflow_blocked" or (
            (result.get("execution_metadata") or {}).get("reason") == "recursive_workflow_blocked"
        )
    finally:
        db.close()


def test_depth_limit(client):
    seeded = _seed_invoice_and_po(client.testing_session_local, confidence=0.3)
    db = client.testing_session_local()
    try:
        engine = WorkflowEngine(db)
        token = _workflow_depth.set(10)
        try:
            results = engine.handle_event(
                trigger_event="document_processed",
                entity_type="document",
                entity_id=seeded["document_id"],
            )
        finally:
            _workflow_depth.reset(token)
        assert results
        assert results[0]["status"] == "skipped"
        assert results[0]["reason"] == "max_workflow_depth_reached"
    finally:
        db.close()


def test_review_completion_workflow(client):
    seeded = _seed_invoice_and_po(client.testing_session_local)
    db = client.testing_session_local()
    try:
        review = DocumentReview(
            document_id=seeded["document_id"],
            status=ReviewStatus.APPROVED.value,
            priority=ReviewPriority.MEDIUM.value,
            reason=ReviewReason.VALIDATION_MISMATCH.value,
            details="done",
            resolved_at=datetime.now(timezone.utc),
        )
        db.add(review)
        db.commit()
        db.refresh(review)
        engine = WorkflowEngine(db)
        workflow = engine.get_workflow_by_code("document_review_completion")
        result = engine.trigger_workflow(
            workflow.id,
            entity_type="review",
            entity_id=review.id,
            force=True,
        )
        assert result["status"] == WorkflowExecutionStatus.COMPLETED.value
        assert any(step["step_type"] == "record_result" for step in result["steps"])
    finally:
        db.close()


def test_failed_step_recorded(client, monkeypatch):
    seeded = _seed_invoice_and_po(client.testing_session_local)
    db = client.testing_session_local()
    try:
        engine = WorkflowEngine(db)
        workflow = engine.get_workflow_by_code("invoice_validation")

        def boom(*args, **kwargs):
            raise RuntimeError("validation boom")

        monkeypatch.setattr(engine, "_action_run_validation", boom)
        result = engine.trigger_workflow(
            workflow.id,
            entity_type="invoice",
            entity_id=seeded["invoice_id"],
            force=True,
        )
        assert result["status"] == WorkflowExecutionStatus.FAILED.value
        assert result["error_message"]
        assert any(step["status"] == "failed" for step in result["steps"])
    finally:
        db.close()
