"""API tests for workflow endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.models.document import Document, DocumentStatus
from app.models.invoice import Invoice


def _seed_document(session_factory):
    db = session_factory()
    try:
        doc = Document(
            original_filename="wf.pdf",
            stored_filename=f"{uuid.uuid4()}.pdf",
            file_type="pdf",
            file_size=10,
            storage_path="storage/uploads/wf.pdf",
            status=DocumentStatus.PROCESSED.value,
            document_type="invoice",
            classification_confidence=0.2,
            uploaded_at=datetime.now(timezone.utc),
        )
        db.add(doc)
        db.flush()
        invoice = Invoice(
            document_id=doc.id,
            vendor_name="WF Vendor",
            invoice_number="INV-API",
            total_amount=10,
            currency="PKR",
            extraction_confidence=0.2,
        )
        db.add(invoice)
        db.commit()
        return {"document_id": doc.id, "invoice_id": invoice.id}
    finally:
        db.close()


def test_list_workflows_api(client):
    response = client.get("/api/v1/workflows")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) >= 3
    assert all("allowed_actions" in item for item in items)


def test_get_workflow_api(client):
    listed = client.get("/api/v1/workflows").json()["items"]
    workflow_id = listed[0]["id"]
    response = client.get(f"/api/v1/workflows/{workflow_id}")
    assert response.status_code == 200
    assert response.json()["id"] == workflow_id


def test_unknown_workflow_rejected(client):
    response = client.get(f"/api/v1/workflows/{uuid.uuid4()}")
    assert response.status_code == 404


def test_trigger_and_list_executions(client):
    seeded = _seed_document(client.testing_session_local)
    workflows = client.get("/api/v1/workflows").json()["items"]
    low_conf = next(item for item in workflows if item["code"] == "low_confidence_review")

    triggered = client.post(
        f"/api/v1/workflows/{low_conf['id']}/trigger",
        json={
            "entity_type": "document",
            "entity_id": str(seeded["document_id"]),
            "force": True,
        },
    )
    assert triggered.status_code == 200
    payload = triggered.json()
    assert payload["status"] in {"completed", "failed", "skipped"}
    assert "steps" in payload

    executions = client.get(f"/api/v1/workflows/{low_conf['id']}/executions")
    assert executions.status_code == 200
    assert executions.json()["total"] >= 1

    detail = client.get(f"/api/v1/workflow-executions/{payload['id']}")
    assert detail.status_code == 200
    assert detail.json()["id"] == payload["id"]


def test_trigger_validation(client):
    workflows = client.get("/api/v1/workflows").json()["items"]
    workflow_id = workflows[0]["id"]
    response = client.post(
        f"/api/v1/workflows/{workflow_id}/trigger",
        json={"entity_type": "", "entity_id": "x"},
    )
    assert response.status_code == 422


def test_existing_health_still_works(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
