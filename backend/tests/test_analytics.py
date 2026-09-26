import uuid
from datetime import datetime, timezone

from app.core.security import create_access_token
from app.models.anomaly import AnomalyStatus, DocumentAnomaly, AnomalyModelRun
from app.models.document import Document, DocumentStatus, DocumentType
from app.models.document_processing_job import DocumentProcessingJob, ProcessingJobStatus
from app.models.document_review import DocumentReview, ReviewReason, ReviewStatus
from app.models.duplicate import DocumentDuplicate, DuplicateDetectionType, DuplicateStatus
from app.models.invoice import Invoice
from app.models.three_way_match import ThreeWayMatch
from app.models.user import UserRole
from app.models.validation import DocumentValidation, ValidationStatus
from app.models.vendor import Vendor


def _headers_for(user) -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject=user.id, role=user.role)}"}


def _seed_document(db, *, filename="a.pdf", status=DocumentStatus.PROCESSED.value, doc_type=DocumentType.INVOICE.value):
    now = datetime.now(timezone.utc)
    doc = Document(
        original_filename=filename,
        stored_filename=f"{uuid.uuid4()}.pdf",
        file_type="pdf",
        file_size=100,
        storage_path=f"storage/{filename}",
        status=status,
        document_type=doc_type,
        uploaded_at=now,
        processed_at=now if status == DocumentStatus.PROCESSED.value else None,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def test_analytics_empty_and_rbac(client, auth_client_factory):
    empty = client.get("/api/v1/analytics/summary")
    assert empty.status_code == 200
    body = empty.json()
    assert body["total_documents"] == 0
    assert body["total_invoices"] == 0
    assert body["total_invoice_value_by_currency"] == []

    viewer = auth_client_factory(
        username="an_viewer",
        email="an_viewer@example.com",
        password="ViewerPass1!",
        role=UserRole.VIEWER.value,
    )
    assert (
        client.get("/api/v1/analytics/summary", headers=_headers_for(viewer.user)).status_code
        == 200
    )

    from fastapi.testclient import TestClient
    from app.main import app as fastapi_app

    bare = TestClient(fastapi_app)
    assert bare.get("/api/v1/analytics/summary").status_code == 401


def test_analytics_populated_counts_and_currency(client):
    db = client.testing_session_local()
    try:
        vendor = Vendor(name="Acme", normalized_name="acme")
        db.add(vendor)
        db.flush()
        d1 = _seed_document(db, filename="inv1.pdf")
        d2 = _seed_document(db, filename="inv2.pdf", status=DocumentStatus.FAILED.value)
        d3 = _seed_document(
            db,
            filename="po1.pdf",
            doc_type=DocumentType.PURCHASE_ORDER.value,
        )
        inv1 = Invoice(
            document_id=d1.id,
            vendor_id=vendor.id,
            vendor_name="Acme",
            invoice_number="INV-1",
            total_amount=1000,
            tax_amount=100,
            currency="USD",
        )
        inv2 = Invoice(
            document_id=d2.id,
            vendor_id=vendor.id,
            vendor_name="Acme",
            invoice_number="INV-2",
            total_amount=50000,
            tax_amount=5000,
            currency="PKR",
        )
        db.add_all([inv1, inv2])
        db.commit()
        doc_id_po = d3.id
        inv1_id = inv1.id
    finally:
        db.close()

    summary = client.get("/api/v1/analytics/summary").json()
    assert summary["total_documents"] >= 3
    assert summary["failed_documents"] >= 1
    assert summary["total_invoices"] >= 2
    currencies = {item["currency"]: item for item in summary["total_invoice_value_by_currency"]}
    assert "USD" in currencies
    assert "PKR" in currencies
    assert currencies["USD"]["total"] == 1000
    assert currencies["PKR"]["total"] == 50000

    documents = client.get("/api/v1/analytics/documents").json()
    assert any(item["name"] == "invoice" for item in documents["by_type"])
    assert documents["processing"]["failed"] >= 1

    invoices = client.get("/api/v1/analytics/invoices").json()
    assert invoices["invoice_count"] >= 2
    assert len(invoices["by_currency"]) >= 2

    vendors = client.get("/api/v1/analytics/vendors?page=1&page_size=10").json()
    assert vendors["total"] >= 2
    assert all("currency" in row for row in vendors["items"])
    # Same vendor can appear in multiple currency rows
    assert any(row["vendor"] == "Acme" for row in vendors["items"])

    # Use seeded ids to avoid unused warnings
    assert inv1_id
    assert doc_id_po


def test_analytics_reviews_validations_anomalies_duplicates_processing(client):
    db = client.testing_session_local()
    try:
        doc = _seed_document(db, filename="rev.pdf")
        inv_doc = _seed_document(db, filename="val-inv.pdf")
        po_doc = _seed_document(db, filename="val-po.pdf", doc_type=DocumentType.PURCHASE_ORDER.value)
        grn_doc = _seed_document(db, filename="val-grn.pdf", doc_type=DocumentType.GOODS_RECEIPT.value)
        invoice = Invoice(document_id=inv_doc.id, vendor_name="V", invoice_number="X", total_amount=10, currency="USD")
        db.add(invoice)
        db.flush()
        from app.models.purchase_order import PurchaseOrder

        po = PurchaseOrder(
            document_id=po_doc.id,
            vendor_name="V",
            po_number="PO-1",
            total_amount=10,
            currency="USD",
        )
        db.add(po)
        db.flush()
        db.add(
            DocumentReview(
                document_id=doc.id,
                status=ReviewStatus.PENDING.value,
                reason=ReviewReason.VALIDATION_MISMATCH.value,
                details="mismatch",
                priority="high",
            )
        )
        db.add(
            DocumentValidation(
                invoice_id=invoice.id,
                purchase_order_id=po.id,
                status=ValidationStatus.MISMATCH.value,
                vendor_match=False,
                currency_match=True,
                subtotal_match=True,
                tax_match=True,
                total_match=False,
                invoice_number="X",
                po_number="PO-1",
            )
        )
        db.add(
            ThreeWayMatch(
                invoice_document_id=inv_doc.id,
                purchase_order_document_id=po_doc.id,
                goods_receipt_document_id=grn_doc.id,
                status="needs_review",
                vendor_status="matched",
                po_reference_status="matched",
                grn_reference_status="matched",
                quantity_status="needs_review",
                financial_status="matched",
                relationship_status="matched",
            )
        )
        run = AnomalyModelRun(
            model_name="isolation_forest",
            model_version="1.0.0",
            status="ready",
            sample_count=10,
            feature_count=5,
        )
        db.add(run)
        db.flush()
        db.add(
            DocumentAnomaly(
                document_id=doc.id,
                model_run_id=run.id,
                anomaly_score=0.9,
                status=AnomalyStatus.ANOMALY.value,
            )
        )
        other = _seed_document(db, filename="dup.pdf")
        db.add(
            DocumentDuplicate(
                source_document_id=doc.id,
                duplicate_document_id=other.id,
                detection_type=DuplicateDetectionType.EXACT_DUPLICATE.value,
                status=DuplicateStatus.PENDING.value,
                similarity_score=1.0,
            )
        )
        now = datetime.now(timezone.utc)
        db.add(
            DocumentProcessingJob(
                document_id=doc.id,
                status=ProcessingJobStatus.COMPLETED.value,
                job_type="document_processing",
                progress=100,
                current_stage="completed",
                started_at=now,
                completed_at=now,
            )
        )
        db.commit()
    finally:
        db.close()

    reviews = client.get("/api/v1/analytics/reviews").json()
    assert reviews["pending"] >= 1
    assert reviews["total"] >= 1
    assert any(item["name"] == "validation_mismatch" for item in reviews["by_reason"])

    validations = client.get("/api/v1/analytics/validations").json()
    assert validations["invoice_po"]["mismatch"] >= 1
    assert validations["three_way"]["needs_review"] >= 1
    assert any(item["name"] == "vendor" for item in validations["mismatch_dimensions"])

    anomalies = client.get("/api/v1/analytics/anomalies").json()
    assert anomalies["anomaly"] >= 1
    assert anomalies["total_scored"] >= 1

    duplicates = client.get("/api/v1/analytics/duplicates").json()
    assert duplicates["exact_duplicate"] >= 1
    assert duplicates["pending"] >= 1

    processing = client.get("/api/v1/analytics/processing").json()
    assert processing["completed"] >= 1
    assert processing["duration_sample_count"] >= 1


def test_analytics_trends_periods(client):
    for period in ("7d", "30d", "90d", "12m"):
        response = client.get(f"/api/v1/analytics/trends?period={period}")
        assert response.status_code == 200
        body = response.json()
        assert body["period"] == period
        assert isinstance(body["points"], list)
        assert len(body["points"]) > 0
