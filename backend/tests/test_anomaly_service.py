"""Tests for anomaly service train/score/persistence."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.models.document import Document, DocumentStatus
from app.models.invoice import Invoice
from app.models.vendor import Vendor
from app.services.anomaly_service import AnomalyService


def _seed_invoices(session_factory, count: int = 12, outlier: bool = True):
    db = session_factory()
    try:
        vendor = Vendor(name="Anomaly Vendor", normalized_name="anomaly vendor")
        db.add(vendor)
        db.flush()
        base = datetime.now(timezone.utc) - timedelta(days=count)
        docs = []
        for i in range(count):
            doc = Document(
                original_filename=f"inv-{i}.pdf",
                stored_filename=f"{uuid.uuid4()}.pdf",
                file_type="pdf",
                file_size=10,
                storage_path=f"storage/uploads/inv-{i}.pdf",
                status=DocumentStatus.PROCESSED.value,
                document_type="invoice",
                uploaded_at=base + timedelta(days=i),
            )
            db.add(doc)
            db.flush()
            amount = 1000 + i * 10
            if outlier and i == count - 1:
                amount = 50000
            invoice = Invoice(
                document_id=doc.id,
                vendor_id=vendor.id,
                vendor_name="Anomaly Vendor",
                invoice_number=f"INV-{i}",
                subtotal=amount * 0.9,
                tax_amount=amount * 0.1,
                total_amount=amount,
                currency="PKR",
                extraction_confidence=0.85,
                created_at=base + timedelta(days=i),
            )
            db.add(invoice)
            docs.append(doc.id)
        db.commit()
        return docs
    finally:
        db.close()


def test_train_insufficient_data(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "ANOMALY_MODEL_DIR", str(tmp_path / "models"))
    monkeypatch.setattr(settings, "ANOMALY_MIN_TRAINING_SAMPLES", 10)
    db = client.testing_session_local()
    try:
        result = AnomalyService(db).train(min_samples=10)
        assert result["status"] == "insufficient_data"
        assert result["sample_count"] < 10
    finally:
        db.close()


def test_train_and_score(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "ANOMALY_MODEL_DIR", str(tmp_path / "models"))
    monkeypatch.setattr(settings, "ANOMALY_MIN_TRAINING_SAMPLES", 10)
    docs = _seed_invoices(client.testing_session_local, count=12)
    db = client.testing_session_local()
    try:
        service = AnomalyService(db)
        run = service.train(min_samples=10)
        assert run["status"] == "ready"
        assert run["sample_count"] >= 10
        assert run["feature_count"] > 0

        scored = service.score_document(docs[-1], force=True)
        assert "anomaly_score" in scored
        assert scored["status"] in {"normal", "unusual", "anomaly", "requires_review"}
        assert scored["reasons"]
        assert all("fraud" not in reason.lower() for reason in scored["reasons"])

        # duplicate scoring returns existing unless force
        again = service.score_document(docs[-1], force=False)
        assert again["id"] == scored["id"]
    finally:
        db.close()


def test_list_and_filters(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "ANOMALY_MODEL_DIR", str(tmp_path / "models"))
    monkeypatch.setattr(settings, "ANOMALY_MIN_TRAINING_SAMPLES", 10)
    docs = _seed_invoices(client.testing_session_local, count=12)
    db = client.testing_session_local()
    try:
        service = AnomalyService(db)
        service.train(min_samples=10)
        service.score_many(docs[:5], force=True)
        listed = service.list_anomalies(page=1, page_size=10, sort_by="anomaly_score")
        assert listed["total"] >= 1
        assert listed["items"]
        vendor_filtered = service.list_anomalies(vendor="Anomaly")
        assert vendor_filtered["total"] >= 1
    finally:
        db.close()
