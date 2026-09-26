"""API tests for anomaly detection endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.models.document import Document, DocumentStatus
from app.models.invoice import Invoice
from app.models.vendor import Vendor


def _seed(session_factory, count: int = 12):
    db = session_factory()
    try:
        vendor = Vendor(name="API Vendor", normalized_name="api vendor")
        db.add(vendor)
        db.flush()
        base = datetime.now(timezone.utc) - timedelta(days=count)
        ids = []
        for i in range(count):
            doc = Document(
                original_filename=f"a-{i}.pdf",
                stored_filename=f"{uuid.uuid4()}.pdf",
                file_type="pdf",
                file_size=10,
                storage_path=f"storage/uploads/a-{i}.pdf",
                status=DocumentStatus.PROCESSED.value,
                document_type="invoice",
                uploaded_at=base + timedelta(days=i),
            )
            db.add(doc)
            db.flush()
            amount = 200 + i
            if i == count - 1:
                amount = 20000
            db.add(
                Invoice(
                    document_id=doc.id,
                    vendor_id=vendor.id,
                    vendor_name="API Vendor",
                    invoice_number=f"A-{i}",
                    total_amount=amount,
                    subtotal=amount * 0.9,
                    tax_amount=amount * 0.1,
                    currency="PKR",
                    created_at=base + timedelta(days=i),
                )
            )
            ids.append(doc.id)
        db.commit()
        return ids
    finally:
        db.close()


def test_train_insufficient_api(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "ANOMALY_MODEL_DIR", str(tmp_path / "models"))
    response = client.post("/api/v1/anomalies/train", json={"min_samples": 10})
    assert response.status_code == 200
    assert response.json()["status"] == "insufficient_data"


def test_train_score_list_api(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "ANOMALY_MODEL_DIR", str(tmp_path / "models"))
    docs = _seed(client.testing_session_local, count=12)

    trained = client.post("/api/v1/anomalies/train", json={"min_samples": 10})
    assert trained.status_code == 200
    assert trained.json()["status"] == "ready"

    scored = client.post(
        "/api/v1/anomalies/score",
        json={"document_id": str(docs[-1]), "force": True},
    )
    assert scored.status_code == 200
    payload = scored.json()
    assert "anomaly_score" in payload
    assert payload["status"] in {"normal", "unusual", "anomaly", "requires_review"}

    listed = client.get("/api/v1/anomalies?page=1&page_size=10")
    assert listed.status_code == 200
    assert listed.json()["total"] >= 1

    detail = client.get(f"/api/v1/anomalies/{docs[-1]}")
    assert detail.status_code == 200

    runs = client.get("/api/v1/anomaly-model-runs")
    assert runs.status_code == 200
    assert runs.json()["total"] >= 1

    summary = client.get("/api/v1/anomalies/summary")
    assert summary.status_code == 200
    assert "disclaimer" in summary.json()


def test_score_without_model(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "ANOMALY_MODEL_DIR", str(tmp_path / "models"))
    response = client.post(
        "/api/v1/anomalies/score",
        json={"document_id": str(uuid.uuid4())},
    )
    assert response.status_code in {400, 404}
