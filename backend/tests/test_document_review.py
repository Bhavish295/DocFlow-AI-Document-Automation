from datetime import datetime, timezone
import io
import uuid

from sqlalchemy import func, select, update

from app.models.document import Document, DocumentStatus, DocumentType
from app.models.document_review import DocumentReview, ReviewReason, ReviewStatus
from app.models.invoice import Invoice
from app.models.purchase_order import PurchaseOrder
from app.models.validation import ValidationStatus
from app.services.document_review import DocumentReviewService
from tests.test_classification import UNKNOWN_TEXT
from tests.test_invoice_extraction import COMPLETE_INVOICE
from tests.test_purchase_order_extraction import COMPLETE_PO


def _upload(client, filename: str = "doc.pdf"):
    return client.post(
        "/api/v1/documents",
        files={"file": (filename, io.BytesIO(b"%PDF-1.4 sample"), "application/pdf")},
    ).json()


def _process(client, monkeypatch, text: str, filename: str = "doc.pdf"):
    created = _upload(client, filename=filename)
    monkeypatch.setattr(
        "app.services.text_extraction.extract_selectable_pdf_text",
        lambda _path: text,
    )
    response = client.post(f"/api/v1/documents/{created['id']}/process")
    return created["id"], response


def _count_reviews(client) -> int:
    db = client.testing_session_local()
    try:
        return db.scalar(select(func.count()).select_from(DocumentReview)) or 0
    finally:
        db.close()


def test_create_review_and_duplicate_prevention(client):
    created = _upload(client)
    db = client.testing_session_local()
    try:
        service = DocumentReviewService(db)
        first = service.create_review_if_needed(
            document_id=uuid.UUID(created["id"]),
            reason=ReviewReason.PROCESSING_FAILED.value,
            priority="high",
            details="Needs review",
        )
        db.commit()
        second = service.create_review_if_needed(
            document_id=uuid.UUID(created["id"]),
            reason=ReviewReason.UNKNOWN_DOCUMENT_TYPE.value,
            priority="medium",
            details="Should not create duplicate",
        )
        db.commit()
        assert first is not None
        assert second is not None
        assert first.id == second.id
        assert (db.scalar(select(func.count()).select_from(DocumentReview)) or 0) == 1
    finally:
        db.close()


def test_list_filter_pagination_and_detail(client):
    first = _upload(client, "one.pdf")
    second = _upload(client, "two.pdf")
    db = client.testing_session_local()
    try:
        service = DocumentReviewService(db)
        service.create_review_if_needed(
            document_id=uuid.UUID(first["id"]),
            reason=ReviewReason.PROCESSING_FAILED.value,
            priority="high",
            details="Fail one",
        )
        service.create_review_if_needed(
            document_id=uuid.UUID(second["id"]),
            reason=ReviewReason.UNKNOWN_DOCUMENT_TYPE.value,
            priority="medium",
            details="Unknown two",
        )
        db.commit()
    finally:
        db.close()

    listed = client.get("/api/v1/reviews", params={"page": 1, "page_size": 1})
    assert listed.status_code == 200
    payload = listed.json()
    assert payload["total"] == 2
    assert payload["total_pages"] == 2
    assert payload["has_next"] is True
    assert len(payload["items"]) == 1

    by_status = client.get("/api/v1/reviews", params={"status": "pending"})
    assert by_status.json()["total"] == 2

    by_priority = client.get("/api/v1/reviews", params={"priority": "high"})
    assert by_priority.json()["total"] == 1

    by_reason = client.get(
        "/api/v1/reviews",
        params={"reason": ReviewReason.UNKNOWN_DOCUMENT_TYPE.value},
    )
    assert by_reason.json()["total"] == 1

    review_id = by_priority.json()["items"][0]["id"]
    detail = client.get(f"/api/v1/reviews/{review_id}")
    assert detail.status_code == 200
    assert detail.json()["document"]["original_filename"] == "one.pdf"


def test_start_approve_reject_and_notes(client):
    created = _upload(client)
    db = client.testing_session_local()
    try:
        review = DocumentReviewService(db).create_review_if_needed(
            document_id=uuid.UUID(created["id"]),
            reason=ReviewReason.MISSING_REQUIRED_FIELDS.value,
            priority="medium",
            details="Missing fields",
        )
        db.commit()
        review_id = str(review.id)
    finally:
        db.close()

    started = client.post(
        f"/api/v1/reviews/{review_id}/start",
        json={"reviewer_notes": "Looking into this"},
    )
    assert started.status_code == 200
    assert started.json()["status"] == "in_review"
    assert started.json()["reviewer_notes"] == "Looking into this"
    assert started.json()["resolved_at"] is None

    approved = client.post(
        f"/api/v1/reviews/{review_id}/approve",
        json={"reviewer_notes": "Looks fine"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert approved.json()["resolved_at"] is not None

    reopened = client.patch(
        f"/api/v1/reviews/{review_id}",
        json={"status": "pending"},
    )
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "pending"
    assert reopened.json()["resolved_at"] is None

    rejected = client.post(
        f"/api/v1/reviews/{review_id}/reject",
        json={"reviewer_notes": "Rejecting"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["resolved_at"] is not None


def test_processing_failed_creates_review(client, monkeypatch):
    document_id, response = _process(client, monkeypatch, "")
    assert response.status_code == 200
    assert response.json()["status"] == "failed"

    reviews = client.get(
        "/api/v1/reviews",
        params={"reason": ReviewReason.PROCESSING_FAILED.value},
    ).json()
    assert reviews["total"] == 1
    assert reviews["items"][0]["document_id"] == document_id
    assert reviews["items"][0]["priority"] == "high"


def test_other_classification_creates_review(client, monkeypatch):
    document_id, response = _process(client, monkeypatch, UNKNOWN_TEXT)
    assert response.status_code == 200
    assert response.json()["document_type"] == "other"

    reviews = client.get(
        "/api/v1/reviews",
        params={"reason": ReviewReason.UNKNOWN_DOCUMENT_TYPE.value},
    ).json()
    assert reviews["total"] >= 1
    assert any(item["document_id"] == document_id for item in reviews["items"])


def test_low_classification_confidence_creates_review(client):
    created = _upload(client)
    db = client.testing_session_local()
    try:
        db.execute(
            update(Document)
            .where(Document.id == uuid.UUID(created["id"]))
            .values(
                status=DocumentStatus.PROCESSED.value,
                document_type=DocumentType.INVOICE.value,
                classification_confidence=0.55,
                extracted_text="invoice content",
            )
        )
        db.commit()
        document = db.get(Document, uuid.UUID(created["id"]))
        DocumentReviewService(db).evaluate_after_processing(document)
        db.commit()
    finally:
        db.close()

    reviews = client.get(
        "/api/v1/reviews",
        params={"reason": ReviewReason.LOW_CLASSIFICATION_CONFIDENCE.value},
    ).json()
    assert reviews["total"] == 1


def test_low_invoice_extraction_confidence_and_missing_fields(client):
    created = _upload(client)
    now = datetime.now(timezone.utc)
    db = client.testing_session_local()
    try:
        document_id = uuid.UUID(created["id"])
        db.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(
                status=DocumentStatus.PROCESSED.value,
                document_type=DocumentType.INVOICE.value,
                classification_confidence=0.95,
                extracted_text="invoice",
            )
        )
        invoice = Invoice(
            document_id=document_id,
            vendor_name=None,
            invoice_number=None,
            invoice_date=None,
            total_amount=None,
            extraction_confidence=0.4,
            created_at=now,
            updated_at=now,
        )
        db.add(invoice)
        db.commit()
        document = db.get(Document, document_id)
        DocumentReviewService(db).evaluate_after_processing(document, invoice=invoice)
        db.commit()
    finally:
        db.close()

    # First active review wins; missing fields is evaluated before low confidence.
    reviews = client.get("/api/v1/reviews").json()
    assert reviews["total"] == 1
    assert reviews["items"][0]["reason"] == ReviewReason.MISSING_REQUIRED_FIELDS.value


def test_validation_mismatch_creates_review_matched_does_not(client, monkeypatch):
    invoice_doc, inv_response = _process(client, monkeypatch, COMPLETE_INVOICE, filename="inv.pdf")
    po_doc, po_response = _process(client, monkeypatch, COMPLETE_PO, filename="po.pdf")
    assert inv_response.status_code == 200
    assert po_response.status_code == 200

    invoice = client.get(f"/api/v1/documents/{invoice_doc}/invoice").json()
    purchase_order = client.get(f"/api/v1/documents/{po_doc}/purchase-order").json()

    before = _count_reviews(client)
    matched = client.post(
        f"/api/v1/validations/invoice/{invoice['id']}/purchase-order/{purchase_order['id']}"
    )
    assert matched.status_code == 200
    assert matched.json()["status"] == ValidationStatus.MATCHED.value
    assert _count_reviews(client) == before

    bad_text = COMPLETE_INVOICE.replace("ABC Pvt Ltd", "XYZ Supplies")
    mismatched_doc, bad_response = _process(client, monkeypatch, bad_text, filename="bad-inv.pdf")
    assert bad_response.status_code == 200
    bad_invoice = client.get(f"/api/v1/documents/{mismatched_doc}/invoice").json()

    before_mismatch = _count_reviews(client)
    mismatched = client.post(
        f"/api/v1/validations/invoice/{bad_invoice['id']}/purchase-order/{purchase_order['id']}"
    )
    assert mismatched.status_code == 200
    assert mismatched.json()["status"] == ValidationStatus.MISMATCH.value
    assert _count_reviews(client) > before_mismatch

    reviews = client.get(
        "/api/v1/reviews",
        params={"reason": ReviewReason.VALIDATION_MISMATCH.value},
    ).json()
    assert reviews["total"] >= 1


def test_requires_review_flag_on_documents(client, monkeypatch):
    document_id, response = _process(client, monkeypatch, UNKNOWN_TEXT)
    assert response.status_code == 200
    listed = client.get("/api/v1/documents").json()
    item = next(doc for doc in listed["items"] if doc["id"] == document_id)
    assert item["requires_review"] is True
