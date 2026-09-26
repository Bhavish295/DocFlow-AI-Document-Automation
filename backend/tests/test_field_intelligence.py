from datetime import date, datetime, timezone
from decimal import Decimal
import io
import uuid

from sqlalchemy import func, select

from app.models.document import Document, DocumentStatus, DocumentType
from app.models.document_review import DocumentReview, ReviewReason
from app.models.invoice import Invoice
from app.models.purchase_order import PurchaseOrder
from app.services.document_review import DocumentReviewService
from app.services.field_intelligence import (
    ISSUE_FINANCIAL_MISMATCH,
    ISSUE_INVALID_DATE,
    ISSUE_LOW_EXTRACTION,
    ISSUE_NEGATIVE_AMOUNT,
    STATUS_INVALID,
    STATUS_MISSING,
    STATUS_SUSPICIOUS,
    STATUS_VALID,
    evaluate_invoice_fields,
    evaluate_purchase_order_fields,
)


def _upload(client, filename: str = "doc.pdf"):
    return client.post(
        "/api/v1/documents",
        files={"file": (filename, io.BytesIO(b"%PDF-1.4 sample"), "application/pdf")},
    ).json()


def _valid_invoice_values(**overrides):
    values = {
        "invoice_number": "INV-1827",
        "invoice_date": date(2026, 9, 10),
        "vendor_name": "ABC Pvt Ltd",
        "subtotal": Decimal("450000.00"),
        "tax_amount": Decimal("81000.00"),
        "total_amount": Decimal("531000.00"),
        "currency": "PKR",
    }
    values.update(overrides)
    return values


def _valid_po_values(**overrides):
    values = {
        "po_number": "PO-7788",
        "po_date": date(2026, 9, 1),
        "vendor_name": "ABC Pvt Ltd",
        "subtotal": Decimal("450000.00"),
        "tax_amount": Decimal("81000.00"),
        "total_amount": Decimal("531000.00"),
        "currency": "PKR",
    }
    values.update(overrides)
    return values


def _field(result, name: str):
    return next(item for item in result.fields if item.field_name == name)


def _seed_record(client, filename: str, document_type: str, model, **fields):
    created = _upload(client, filename)
    db = client.testing_session_local()
    document_id = uuid.UUID(created["id"])
    document = db.get(Document, document_id)
    document.document_type = document_type
    document.status = DocumentStatus.PROCESSED.value
    document.classification_confidence = 0.95
    now = datetime.now(timezone.utc)
    extraction_confidence = fields.pop("extraction_confidence", 0.95)
    record = model(
        document_id=document_id,
        extraction_confidence=extraction_confidence,
        created_at=now,
        updated_at=now,
        **fields,
    )
    db.add(record)
    db.commit()
    db.refresh(document)
    db.refresh(record)
    return db, document, record


def test_complete_valid_invoice():
    result = evaluate_invoice_fields(_valid_invoice_values(), extraction_confidence=0.95)
    assert result.overall_status == "valid"
    assert result.overall_confidence == 1.0
    assert result.review_required is False
    assert result.issues == []
    assert all(item.status == STATUS_VALID and item.confidence == 1.0 for item in result.fields)
    assert _field(result, "invoice_number").value == "INV-1827"
    assert _field(result, "vendor_name").value == "ABC Pvt Ltd"


def test_missing_invoice_number():
    result = evaluate_invoice_fields(_valid_invoice_values(invoice_number="  "))
    item = _field(result, "invoice_number")
    assert item.status == STATUS_MISSING
    assert item.confidence == 0.0
    assert item.value == "  "
    assert result.review_required is True
    assert "field_missing" in result.issues


def test_missing_vendor():
    result = evaluate_invoice_fields(_valid_invoice_values(vendor_name=None))
    item = _field(result, "vendor_name")
    assert item.status == STATUS_MISSING
    assert item.value is None
    assert result.review_required is True


def test_invalid_date():
    result = evaluate_invoice_fields(_valid_invoice_values(invoice_date="31-02-2026"))
    item = _field(result, "invoice_date")
    assert item.status == STATUS_INVALID
    assert item.value == "31-02-2026"
    assert ISSUE_INVALID_DATE in item.issues
    assert result.review_required is True


def test_negative_amount():
    result = evaluate_invoice_fields(_valid_invoice_values(total_amount=Decimal("-15.00")))
    item = _field(result, "total_amount")
    assert item.status == STATUS_INVALID
    assert item.value == -15.0
    assert ISSUE_NEGATIVE_AMOUNT in item.issues
    assert result.review_required is True


def test_subtotal_tax_equals_total():
    values = _valid_invoice_values(
        subtotal=Decimal("10.00"),
        tax_amount=Decimal("0.00"),
        total_amount=Decimal("10.00"),
    )
    result = evaluate_invoice_fields(values)
    assert ISSUE_FINANCIAL_MISMATCH not in result.issues
    assert _field(result, "subtotal").status == STATUS_VALID
    assert _field(result, "tax_amount").status == STATUS_VALID
    assert _field(result, "total_amount").value == 10.0

    near = evaluate_invoice_fields(
        _valid_invoice_values(
            subtotal=Decimal("10.00"),
            tax_amount=Decimal("2.00"),
            total_amount=Decimal("12.01"),
        )
    )
    assert ISSUE_FINANCIAL_MISMATCH not in near.issues


def test_subtotal_tax_total_mismatch():
    original_total = Decimal("20.00")
    result = evaluate_invoice_fields(
        _valid_invoice_values(
            subtotal=Decimal("10.00"),
            tax_amount=Decimal("2.00"),
            total_amount=original_total,
        )
    )
    assert ISSUE_FINANCIAL_MISMATCH in result.issues
    for name in ("subtotal", "tax_amount", "total_amount"):
        item = _field(result, name)
        assert item.status == STATUS_SUSPICIOUS
        assert item.confidence == 0.45
        assert ISSUE_FINANCIAL_MISMATCH in item.issues
    assert _field(result, "total_amount").value == 20.0
    assert result.review_required is True


def test_valid_currency():
    for raw in ("PKR", "usd", "EUR", "GBP", "$", "£"):
        result = evaluate_invoice_fields(_valid_invoice_values(currency=raw))
        item = _field(result, "currency")
        assert item.status == STATUS_VALID
        assert item.value == raw


def test_missing_currency():
    result = evaluate_invoice_fields(_valid_invoice_values(currency=None))
    item = _field(result, "currency")
    assert item.status == STATUS_MISSING
    assert item.value is None
    assert result.review_required is True
    assert "field_missing" in result.issues


def test_complete_valid_purchase_order():
    result = evaluate_purchase_order_fields(_valid_po_values(), extraction_confidence=0.91)
    assert result.document_type == "purchase_order"
    assert result.overall_status == "valid"
    assert result.overall_confidence == 1.0
    assert result.review_required is False
    assert _field(result, "po_number").value == "PO-7788"


def test_missing_po_number():
    result = evaluate_purchase_order_fields(_valid_po_values(po_number=None))
    item = _field(result, "po_number")
    assert item.status == STATUS_MISSING
    assert item.value is None
    assert result.review_required is True


def test_low_extraction_confidence_lowers_field_confidence_without_inventing_values():
    values = _valid_invoice_values()
    result = evaluate_invoice_fields(values, extraction_confidence=0.4)
    assert ISSUE_LOW_EXTRACTION in result.issues
    assert result.review_required is True
    assert result.overall_status == "needs_review"
    assert result.overall_confidence == 0.4
    for item in result.fields:
        assert item.status == STATUS_VALID
        assert item.confidence == 0.4
    assert _field(result, "invoice_number").value == values["invoice_number"]
    assert _field(result, "total_amount").value == 531000.0


def test_review_created_for_financial_mismatch(client):
    db, document, invoice = _seed_record(
        client,
        "mismatch.pdf",
        DocumentType.INVOICE.value,
        Invoice,
        vendor_name="ABC Pvt Ltd",
        invoice_number="INV-9",
        invoice_date=date(2026, 9, 10),
        subtotal=Decimal("10.00"),
        tax_amount=Decimal("2.00"),
        total_amount=Decimal("20.00"),
        currency="USD",
        extraction_confidence=0.95,
    )
    try:
        DocumentReviewService(db).evaluate_after_processing(document, invoice=invoice)
        db.commit()
        reviews = db.scalars(
            select(DocumentReview).where(DocumentReview.document_id == document.id)
        ).all()
        assert len(reviews) == 1
        assert reviews[0].reason == ReviewReason.FINANCIAL_CONSISTENCY_MISMATCH.value
        assert reviews[0].status == "pending"
        assert float(invoice.total_amount) == 20.0
        assert float(invoice.subtotal) == 10.0
    finally:
        db.close()


def test_duplicate_active_review_is_not_created(client):
    db, document, invoice = _seed_record(
        client,
        "duplicate-review.pdf",
        DocumentType.INVOICE.value,
        Invoice,
        vendor_name="ABC Pvt Ltd",
        invoice_number="INV-9",
        invoice_date=date(2026, 9, 10),
        subtotal=Decimal("10.00"),
        tax_amount=Decimal("2.00"),
        total_amount=Decimal("20.00"),
        currency="USD",
    )
    try:
        service = DocumentReviewService(db)
        service.create_review_if_needed(
            document_id=document.id,
            reason=ReviewReason.PROCESSING_FAILED.value,
            priority="high",
            details="Already open",
        )
        db.commit()
        service.evaluate_after_processing(document, invoice=invoice)
        db.commit()
        count = db.scalar(
            select(func.count())
            .select_from(DocumentReview)
            .where(DocumentReview.document_id == document.id)
        )
        reason = db.scalar(
            select(DocumentReview.reason).where(DocumentReview.document_id == document.id)
        )
        assert count == 1
        assert reason == ReviewReason.PROCESSING_FAILED.value
    finally:
        db.close()


def test_existing_review_reasons_still_work(client):
    reasons = [
        ReviewReason.PROCESSING_FAILED.value,
        ReviewReason.MISSING_REQUIRED_FIELDS.value,
        ReviewReason.VALIDATION_MISMATCH.value,
        ReviewReason.LOW_EXTRACTION_CONFIDENCE.value,
        ReviewReason.LOW_CLASSIFICATION_CONFIDENCE.value,
        ReviewReason.UNKNOWN_DOCUMENT_TYPE.value,
    ]
    db = client.testing_session_local()
    try:
        service = DocumentReviewService(db)
        for index, reason in enumerate(reasons):
            created = _upload(client, f"reason-{index}.pdf")
            service.create_review_if_needed(
                document_id=uuid.UUID(created["id"]),
                reason=reason,
                priority="medium",
                details=f"Existing reason {reason}",
            )
        db.commit()
    finally:
        db.close()

    listed = client.get("/api/v1/reviews", params={"reason": ReviewReason.MISSING_REQUIRED_FIELDS.value})
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    mismatch = client.get("/api/v1/reviews", params={"reason": ReviewReason.VALIDATION_MISMATCH.value})
    assert mismatch.json()["total"] == 1
    failed = client.get("/api/v1/reviews", params={"reason": ReviewReason.PROCESSING_FAILED.value})
    assert failed.json()["total"] == 1


def test_api_invoice_field_intelligence(client):
    db, document, invoice = _seed_record(
        client,
        "api-invoice.pdf",
        DocumentType.INVOICE.value,
        Invoice,
        vendor_name="Northwind",
        invoice_number="INV-1827",
        invoice_date=date(2026, 9, 10),
        subtotal=Decimal("100.00"),
        tax_amount=Decimal("10.00"),
        total_amount=Decimal("110.00"),
        currency="GBP",
        extraction_confidence=0.95,
    )
    document_id = str(document.id)
    db.close()

    before = client.get("/api/v1/reviews").json()["total"]
    response = client.get(f"/api/v1/documents/{document_id}/field-intelligence")
    assert response.status_code == 200
    payload = response.json()
    assert payload["document_id"] == document_id
    assert payload["document_type"] == "invoice"
    assert payload["overall_status"] == "valid"
    assert payload["overall_confidence"] == 1.0
    assert payload["review_required"] is False
    assert payload["issues"] == []
    number = next(item for item in payload["fields"] if item["field_name"] == "invoice_number")
    assert number["value"] == "INV-1827"
    assert number["status"] == "valid"
    assert number["confidence"] == 1.0
    assert number["issues"] == []
    assert client.get("/api/v1/reviews").json()["total"] == before


def test_api_purchase_order_field_intelligence(client):
    db, document, _purchase_order = _seed_record(
        client,
        "api-po.pdf",
        DocumentType.PURCHASE_ORDER.value,
        PurchaseOrder,
        vendor_name="Northwind",
        po_number="PO-7788",
        po_date=date(2026, 9, 1),
        subtotal=Decimal("100.00"),
        tax_amount=Decimal("10.00"),
        total_amount=Decimal("110.00"),
        currency="EUR",
        extraction_confidence=0.9,
    )
    document_id = str(document.id)
    db.close()

    response = client.get(f"/api/v1/documents/{document_id}/field-intelligence")
    assert response.status_code == 200
    payload = response.json()
    assert payload["document_type"] == "purchase_order"
    assert payload["overall_status"] == "valid"
    assert payload["review_required"] is False
    po_number = next(item for item in payload["fields"] if item["field_name"] == "po_number")
    assert po_number["value"] == "PO-7788"
    assert po_number["status"] == "valid"


def test_api_missing_extraction_data(client):
    created = _upload(client, "no-extract.pdf")
    db = client.testing_session_local()
    try:
        document = db.get(Document, uuid.UUID(created["id"]))
        document.document_type = DocumentType.INVOICE.value
        document.status = DocumentStatus.PROCESSED.value
        db.commit()
    finally:
        db.close()

    response = client.get(f"/api/v1/documents/{created['id']}/field-intelligence")
    assert response.status_code == 200
    payload = response.json()
    assert payload["document_type"] == "invoice"
    assert payload["overall_status"] == "unavailable"
    assert payload["overall_confidence"] == 0.0
    assert payload["fields"] == []
    assert payload["issues"] == ["extraction_data_missing"]
    assert payload["review_required"] is False

    missing = client.get(f"/api/v1/documents/{uuid.uuid4()}/field-intelligence")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Document not found."
