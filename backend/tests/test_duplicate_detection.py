"""Service-level duplicate detection tests."""

from __future__ import annotations

from datetime import date
import uuid

from sqlalchemy import select

from app.core.config import settings
from app.core.exceptions import AppError
from app.models.document import Document, DocumentStatus
from app.models.duplicate import DocumentDuplicate, DuplicateDetectionType, DuplicateStatus
from app.models.invoice import Invoice
from app.services.document_hashing import sha256_bytes
from app.services.duplicate_detection import DuplicateDetectionService, normalize_pair


def _doc(db, *, name: str, content_hash: str | None = None, text: str | None = None, doc_type="invoice"):
    document = Document(
        original_filename=name,
        stored_filename=f"{uuid.uuid4()}.pdf",
        file_type="pdf",
        file_size=20,
        storage_path=f"storage/uploads/{name}",
        content_hash=content_hash,
        status=DocumentStatus.PROCESSED.value,
        document_type=doc_type,
        extracted_text=text,
    )
    db.add(document)
    db.flush()
    return document


def test_normalize_pair_orders_and_blocks_self():
    left = uuid.UUID("00000000-0000-0000-0000-000000000001")
    right = uuid.UUID("00000000-0000-0000-0000-000000000002")
    assert normalize_pair(right, left) == (left, right)
    try:
        normalize_pair(left, left)
        assert False, "expected AppError"
    except AppError as exc:
        assert "cannot be a duplicate of itself" in exc.message


def test_exact_duplicate_detection(client):
    db = client.testing_session_local()
    try:
        digest = sha256_bytes(b"same-bytes")
        first = _doc(db, name="one.pdf", content_hash=digest)
        second = _doc(db, name="two.pdf", content_hash=digest)
        other = _doc(db, name="other.pdf", content_hash=sha256_bytes(b"different"))
        db.commit()

        service = DuplicateDetectionService(db)
        result = service.check_document(second.id)
        types = {item["detection_type"] for item in result["items"]}
        assert DuplicateDetectionType.EXACT_DUPLICATE.value in types
        assert result["created_count"] >= 1

        pairs = [
            (row.source_document_id, row.duplicate_document_id)
            for row in db.scalars(
                select(DocumentDuplicate).where(
                    DocumentDuplicate.detection_type
                    == DuplicateDetectionType.EXACT_DUPLICATE.value
                )
            ).all()
        ]
        assert any(first.id in pair and second.id in pair for pair in pairs)
        assert not any(other.id in pair and second.id in pair for pair in pairs)
    finally:
        db.close()


def test_business_duplicate_same_vendor_invoice_number(client):
    db = client.testing_session_local()
    try:
        left = _doc(db, name="inv-a.pdf")
        right = _doc(db, name="inv-b.pdf")
        db.add_all(
            [
                Invoice(
                    document_id=left.id,
                    vendor_name="Acme Supplies",
                    invoice_number="INV-100",
                    total_amount=250.00,
                    currency="USD",
                    invoice_date=date(2024, 1, 15),
                ),
                Invoice(
                    document_id=right.id,
                    vendor_name="  acme   supplies ",
                    invoice_number="inv-100",
                    total_amount=250.00,
                    currency="USD",
                    invoice_date=date(2024, 1, 15),
                ),
            ]
        )
        db.commit()

        result = DuplicateDetectionService(db).check_document(right.id)
        business = [
            item
            for item in result["items"]
            if item["detection_type"] == DuplicateDetectionType.BUSINESS_DUPLICATE.value
        ]
        assert len(business) == 1
        assert business[0]["confidence"] >= 0.85
        assert any("vendor" in reason.lower() for reason in business[0]["reasons"])
    finally:
        db.close()


def test_business_missing_fields_safe(client):
    db = client.testing_session_local()
    try:
        left = _doc(db, name="miss-a.pdf")
        right = _doc(db, name="miss-b.pdf")
        db.add_all(
            [
                Invoice(document_id=left.id, vendor_name="Vendor", invoice_number=None),
                Invoice(document_id=right.id, vendor_name="Vendor", invoice_number=None),
            ]
        )
        db.commit()
        result = DuplicateDetectionService(db).check_document(right.id)
        business = [
            item
            for item in result["items"]
            if item["detection_type"] == DuplicateDetectionType.BUSINESS_DUPLICATE.value
        ]
        assert business == []
    finally:
        db.close()


def test_similar_text_detection(client, monkeypatch):
    monkeypatch.setattr(settings, "DUPLICATE_SIMILARITY_THRESHOLD", 0.5)
    db = client.testing_session_local()
    try:
        text = "Acme invoice for consulting services total amount one thousand dollars"
        left = _doc(db, name="sim-a.pdf", text=text)
        right = _doc(db, name="sim-b.pdf", text=text + " consulting services")
        db.commit()
        result = DuplicateDetectionService(db).check_document(right.id)
        similar = [
            item
            for item in result["items"]
            if item["detection_type"] == DuplicateDetectionType.SIMILAR_DUPLICATE.value
        ]
        assert len(similar) >= 1
        assert similar[0]["similarity_score"] is not None
    finally:
        db.close()


def test_pair_uniqueness_and_reverse_prevention(client):
    db = client.testing_session_local()
    try:
        digest = sha256_bytes(b"pair-bytes")
        left = _doc(db, name="p1.pdf", content_hash=digest)
        right = _doc(db, name="p2.pdf", content_hash=digest)
        db.commit()
        service = DuplicateDetectionService(db)
        first = service.check_document(left.id)
        second = service.check_document(right.id)
        assert first["created_count"] >= 1
        assert second["created_count"] == 0

        rows = list(
            db.scalars(
                select(DocumentDuplicate).where(
                    DocumentDuplicate.detection_type
                    == DuplicateDetectionType.EXACT_DUPLICATE.value
                )
            ).all()
        )
        assert len(rows) == 1
        source_id, duplicate_id = normalize_pair(left.id, right.id)
        assert rows[0].source_document_id == source_id
        assert rows[0].duplicate_document_id == duplicate_id
    finally:
        db.close()


def test_resolve_confirm_dismiss_no_deletion(client):
    db = client.testing_session_local()
    try:
        digest = sha256_bytes(b"resolve-bytes")
        left = _doc(db, name="r1.pdf", content_hash=digest)
        right = _doc(db, name="r2.pdf", content_hash=digest)
        db.commit()
        service = DuplicateDetectionService(db)
        service.check_document(left.id)
        row = db.scalars(select(DocumentDuplicate)).one()
        confirmed = service.resolve_duplicate(row.id, "confirmed")
        assert confirmed["status"] == DuplicateStatus.CONFIRMED.value
        assert confirmed["resolved_at"] is not None
        dismissed = service.resolve_duplicate(row.id, "dismissed")
        assert dismissed["status"] == DuplicateStatus.DISMISSED.value

        assert db.get(Document, left.id) is not None
        assert db.get(Document, right.id) is not None
        assert len(list(db.scalars(select(DocumentDuplicate)).all())) == 1
    finally:
        db.close()
