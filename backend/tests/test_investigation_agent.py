"""Tests for InvestigationAgent orchestration and SQL safety reuse."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.models.document import Document, DocumentStatus
from app.models.document_review import DocumentReview, ReviewPriority, ReviewReason, ReviewStatus
from app.models.invoice import Invoice
from app.models.purchase_order import PurchaseOrder
from app.models.validation import DocumentValidation, ValidationStatus
from app.models.vendor import Vendor
from app.services.investigation_agent import InvestigationAgent
from app.services.investigation_planner import InvestigationPlan, PlannedQuery
from app.services.sql_guard import validate_readonly_sql


def _seed(session_factory):
    db = session_factory()
    try:
        vendor = Vendor(name="ABC Traders", normalized_name="abc traders")
        db.add(vendor)
        db.flush()

        doc = Document(
            original_filename="inv-review.pdf",
            stored_filename=f"{uuid.uuid4()}.pdf",
            file_type="pdf",
            file_size=100,
            storage_path="storage/uploads/inv-review.pdf",
            status=DocumentStatus.MANUAL_REVIEW.value,
            document_type="invoice",
            classification_confidence=0.4,
            uploaded_at=datetime.now(timezone.utc),
        )
        doc_po = Document(
            original_filename="po-review.pdf",
            stored_filename=f"{uuid.uuid4()}.pdf",
            file_type="pdf",
            file_size=120,
            storage_path="storage/uploads/po-review.pdf",
            status=DocumentStatus.PROCESSED.value,
            document_type="purchase_order",
            uploaded_at=datetime.now(timezone.utc),
        )
        db.add_all([doc, doc_po])
        db.flush()

        invoice = Invoice(
            document_id=doc.id,
            vendor_id=vendor.id,
            vendor_name="ABC Traders",
            invoice_number="INV-100",
            total_amount=1000,
            currency="PKR",
            extraction_confidence=0.5,
        )
        po = PurchaseOrder(
            document_id=doc_po.id,
            vendor_id=vendor.id,
            vendor_name="ABC Traders",
            po_number="PO-100",
            total_amount=900,
            currency="PKR",
        )
        db.add_all([invoice, po])
        db.flush()

        db.add(
            DocumentValidation(
                invoice_id=invoice.id,
                purchase_order_id=po.id,
                status=ValidationStatus.MISMATCH.value,
                vendor_match=True,
                total_match=False,
                mismatch_summary="Total mismatch",
            )
        )
        db.add(
            DocumentReview(
                document_id=doc.id,
                status=ReviewStatus.PENDING.value,
                priority=ReviewPriority.HIGH.value,
                reason=ReviewReason.VALIDATION_MISMATCH.value,
                details="Validation mismatch needs review",
            )
        )
        db.commit()
    finally:
        db.close()


def test_investigation_agent_completed(client):
    _seed(client.testing_session_local)
    db = client.testing_session_local()
    try:
        result = InvestigationAgent(db).investigate("Why are invoices being sent to review?")
    finally:
        db.close()

    assert result["status"] == "completed"
    assert result["findings"]
    assert result["evidence"]
    assert result["queries"]
    assert all(step.get("sql") for step in result["queries"])
    types = {finding["type"] for finding in result["findings"]}
    assert types.issubset({"fact", "observation", "inference"})


def test_investigation_agent_specific_invoice_attention(client):
    _seed(client.testing_session_local)
    db = client.testing_session_local()
    try:
        result = InvestigationAgent(db).investigate(
            "Why does invoice INV-100 need attention?"
        )
    finally:
        db.close()

    assert result["status"] == "completed"
    assert result["queries"]
    assert any("INV-100" in (step.get("sql") or "") for step in result["queries"])
    joined = " ".join(finding["description"] for finding in result["findings"])
    assert "INV-100" in joined
    assert "validation_mismatch" in joined or "review" in joined.lower()


def test_investigation_agent_unsupported(client):
    db = client.testing_session_local()
    try:
        result = InvestigationAgent(db).investigate("Launch rockets based on invoice data")
    finally:
        db.close()
    assert result["status"] == "unsupported"
    assert result["findings"] == []
    assert result["queries"] == []


def test_investigation_rejects_write_sql_via_guard(client):
    class UnsafeProvider:
        def plan(self, question: str):
            return InvestigationPlan(
                template_id="unsafe",
                title="unsafe",
                status="ready",
                queries=(
                    PlannedQuery(
                        step_id="bad",
                        question="delete",
                        sql="DELETE FROM invoices",
                        analysis_key="mismatch_count",
                    ),
                ),
            )

    db = client.testing_session_local()
    try:
        result = InvestigationAgent(db, provider=UnsafeProvider()).investigate("test")
    finally:
        db.close()

    assert result["status"] == "failed"
    assert result["queries"][0]["status"] == "rejected"
    assert validate_readonly_sql("DELETE FROM invoices").valid is False


def test_investigation_handles_sql_error(client, monkeypatch):
    from app.services import investigation_agent as module

    class Boom(Exception):
        pass

    def boom_execute(*args, **kwargs):
        raise Boom("db down")

    monkeypatch.setattr(module, "execute_readonly_sql", boom_execute)

    db = client.testing_session_local()
    try:
        result = InvestigationAgent(db).investigate("Which documents require attention?")
    finally:
        db.close()

    assert result["status"] == "failed"
    assert result["findings"] == []


def test_multiple_investigation_steps(client):
    _seed(client.testing_session_local)
    db = client.testing_session_local()
    try:
        result = InvestigationAgent(db).investigate(
            "Which vendors have the most invoice validation mismatches?"
        )
    finally:
        db.close()
    assert result["status"] == "completed"
    assert len(result["queries"]) >= 2
