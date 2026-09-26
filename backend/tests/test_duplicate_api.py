"""API tests for duplicate detection endpoints."""

from __future__ import annotations

from datetime import date
import uuid

from app.models.document import Document, DocumentStatus
from app.models.invoice import Invoice
from app.services.document_hashing import sha256_bytes


def _seed_pair(session_factory, *, same_hash: bool = True):
    db = session_factory()
    try:
        digest_a = sha256_bytes(b"api-dup-a")
        digest_b = digest_a if same_hash else sha256_bytes(b"api-dup-b")
        left = Document(
            original_filename="api-a.pdf",
            stored_filename=f"{uuid.uuid4()}.pdf",
            file_type="pdf",
            file_size=12,
            storage_path="storage/uploads/api-a.pdf",
            content_hash=digest_a,
            status=DocumentStatus.PROCESSED.value,
            document_type="invoice",
            extracted_text="Acme invoice INV-API-1 total 400 USD consulting",
        )
        right = Document(
            original_filename="api-b.pdf",
            stored_filename=f"{uuid.uuid4()}.pdf",
            file_type="pdf",
            file_size=12,
            storage_path="storage/uploads/api-b.pdf",
            content_hash=digest_b,
            status=DocumentStatus.PROCESSED.value,
            document_type="invoice",
            extracted_text="Acme invoice INV-API-1 total 400 USD consulting services",
        )
        db.add_all([left, right])
        db.flush()
        db.add_all(
            [
                Invoice(
                    document_id=left.id,
                    vendor_name="Acme API",
                    invoice_number="INV-API-1",
                    total_amount=400,
                    currency="USD",
                    invoice_date=date(2024, 5, 1),
                ),
                Invoice(
                    document_id=right.id,
                    vendor_name="Acme API",
                    invoice_number="INV-API-1",
                    total_amount=400,
                    currency="USD",
                    invoice_date=date(2024, 5, 1),
                ),
            ]
        )
        db.commit()
        return left.id, right.id
    finally:
        db.close()


def test_check_list_filter_sort_resolve_summary(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "DUPLICATE_SIMILARITY_THRESHOLD", 0.4)
    left_id, right_id = _seed_pair(client.testing_session_local, same_hash=True)

    checked = client.post(f"/api/v1/duplicates/check/{right_id}")
    assert checked.status_code == 200
    payload = checked.json()
    assert payload["document_id"] == str(right_id)
    assert payload["created_count"] >= 1
    assert len(payload["items"]) >= 1

    listed = client.get(
        "/api/v1/duplicates",
        params={
            "status": "pending",
            "detection_type": "exact_duplicate",
            "page": 1,
            "page_size": 10,
            "sort_by": "detected_at",
            "sort_order": "desc",
        },
    )
    assert listed.status_code == 200
    listed_payload = listed.json()
    assert listed_payload["total"] >= 1
    assert listed_payload["page"] == 1

    for_doc = client.get(f"/api/v1/duplicates/{right_id}")
    assert for_doc.status_code == 200
    assert for_doc.json()["total"] >= 1

    duplicate_id = for_doc.json()["items"][0]["id"]
    bad = client.patch(f"/api/v1/duplicates/{duplicate_id}", json={"status": "deleted"})
    assert bad.status_code == 400

    confirmed = client.patch(
        f"/api/v1/duplicates/{duplicate_id}",
        json={"status": "confirmed"},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"

    dismissed = client.patch(
        f"/api/v1/duplicates/{duplicate_id}",
        json={"status": "dismissed"},
    )
    assert dismissed.status_code == 200
    assert dismissed.json()["status"] == "dismissed"

    summary = client.get("/api/v1/duplicates/summary")
    assert summary.status_code == 200
    body = summary.json()
    for key in ("exact", "business", "similar", "pending", "confirmed", "dismissed", "total"):
        assert key in body

    # Documents are never deleted by duplicate APIs.
    left_doc = client.get(f"/api/v1/documents/{left_id}")
    right_doc = client.get(f"/api/v1/documents/{right_id}")
    assert left_doc.status_code == 200
    assert right_doc.status_code == 200


def test_upload_stores_content_hash_without_auto_detection(client):
    content = b"%PDF-1.4 duplicate-upload-test"
    files = {"file": ("upload-dup.pdf", content, "application/pdf")}
    response = client.post("/api/v1/documents", files=files)
    assert response.status_code == 201
    payload = response.json()
    assert payload["content_hash"]
    assert payload["content_hash"] == sha256_bytes(content)
    assert payload.get("duplicate_count", 0) == 0

    listed = client.get("/api/v1/duplicates")
    assert listed.status_code == 200
    assert listed.json()["total"] == 0


def test_invalid_status_filter(client):
    response = client.get("/api/v1/duplicates", params={"status": "nuked"})
    assert response.status_code == 400
