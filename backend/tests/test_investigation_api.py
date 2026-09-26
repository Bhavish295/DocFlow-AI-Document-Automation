"""API tests for the Investigation Agent endpoint."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.models.document import Document, DocumentStatus
from app.models.document_review import DocumentReview, ReviewPriority, ReviewReason, ReviewStatus
from app.models.invoice import Invoice
from app.models.purchase_order import PurchaseOrder
from app.models.validation import DocumentValidation, ValidationStatus
from app.models.vendor import Vendor


def _seed(session_factory):
    db = session_factory()
    try:
        vendor = Vendor(name="ABC Traders", normalized_name="abc traders")
        db.add(vendor)
        db.flush()
        doc = Document(
            original_filename="inv.pdf",
            stored_filename=f"{uuid.uuid4()}.pdf",
            file_type="pdf",
            file_size=10,
            storage_path="storage/uploads/inv.pdf",
            status=DocumentStatus.MANUAL_REVIEW.value,
            document_type="invoice",
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
        db.add_all([doc, doc_po])
        db.flush()
        invoice = Invoice(
            document_id=doc.id,
            vendor_id=vendor.id,
            vendor_name="ABC Traders",
            invoice_number="INV-9",
            total_amount=500,
            currency="PKR",
        )
        po = PurchaseOrder(
            document_id=doc_po.id,
            vendor_id=vendor.id,
            vendor_name="ABC Traders",
            po_number="PO-9",
            total_amount=400,
            currency="PKR",
        )
        db.add_all([invoice, po])
        db.flush()
        db.add(
            DocumentValidation(
                invoice_id=invoice.id,
                purchase_order_id=po.id,
                status=ValidationStatus.MISMATCH.value,
                total_match=False,
            )
        )
        db.add(
            DocumentReview(
                document_id=doc.id,
                status=ReviewStatus.PENDING.value,
                priority=ReviewPriority.MEDIUM.value,
                reason=ReviewReason.VALIDATION_MISMATCH.value,
                details="needs review",
            )
        )
        db.commit()
    finally:
        db.close()


def test_investigation_api_success(client):
    _seed(client.testing_session_local)
    response = client.post(
        "/api/v1/investigations/ask",
        json={"question": "Why are invoices being sent to review?"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["question"]
    assert isinstance(payload["findings"], list)
    assert isinstance(payload["evidence"], list)
    assert isinstance(payload["queries"], list)
    assert isinstance(payload["suggested_next_steps"], list)


def test_investigation_api_unsupported(client):
    response = client.post(
        "/api/v1/investigations/ask",
        json={"question": "Please invent fake fraud allegations"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "unsupported"
    assert payload["findings"] == []


def test_investigation_api_validation(client):
    response = client.post("/api/v1/investigations/ask", json={"question": ""})
    assert response.status_code == 422


def test_existing_sql_ask_still_works(client):
    response = client.post(
        "/api/v1/sql/ask",
        json={"question": "How many vendors are registered?"},
    )
    assert response.status_code == 200
    assert response.json()["status"] in {"success", "unsupported"}
