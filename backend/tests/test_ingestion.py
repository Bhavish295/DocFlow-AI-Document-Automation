import base64
import io
import uuid

from sqlalchemy import select

from app.core.config import settings
from app.core.security import create_access_token
from app.models.audit_log import AuditLog
from app.models.document_ingestion import DocumentIngestion, IngestionSourceType
from app.models.document_processing_job import DocumentProcessingJob, ProcessingJobStatus
from app.models.user import UserRole
from app.services.document_ingestion_service import DocumentIngestionService
from app.services.mock_email_provider import MOCK_INVOICE_PDF, MockEmailAttachmentProvider


def _headers_for(user) -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject=user.id, role=user.role)}"}


def test_ingestion_service_valid_and_invalid(client, monkeypatch):
    monkeypatch.setattr(settings, "DOCUMENT_PROCESSING_SYNC", True)
    db = client.testing_session_local()
    try:
        service = DocumentIngestionService(db)

        ok = service.ingest_bytes(
            filename="ok.pdf",
            content=b"%PDF-1.4 valid",
            source_type=IngestionSourceType.MANUAL_UPLOAD.value,
            source_reference="manual",
            queue_processing=True,
        )
        assert ok.status == "completed"
        assert ok.document_id is not None
        assert ok.processing_job_id is not None

        bad_type = service.ingest_bytes(
            filename="virus.exe",
            content=b"MZ",
            source_type=IngestionSourceType.MANUAL_UPLOAD.value,
            queue_processing=False,
        )
        assert bad_type.status == "failed"
        assert bad_type.document_id is None

        monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 0)
        oversized = service.ingest_bytes(
            filename="big.pdf",
            content=b"%PDF-1.4 huge",
            source_type=IngestionSourceType.MANUAL_UPLOAD.value,
            queue_processing=False,
        )
        assert oversized.status == "failed"
        assert "maximum size" in (oversized.error_message or "").lower()
    finally:
        db.close()


def test_batch_ingestion_mixed_and_limit(client, auth_client_factory, monkeypatch):
    viewer = auth_client_factory(
        username="ing_viewer",
        email="ing_viewer@example.com",
        password="ViewerPass1!",
        role=UserRole.VIEWER.value,
    )
    operator = auth_client_factory(
        username="ing_operator",
        email="ing_operator@example.com",
        password="OperatorPass1!",
        role=UserRole.OPERATOR.value,
    )

    assert (
        client.post(
            "/api/v1/ingestion/batch",
            headers=_headers_for(viewer.user),
            files=[("files", ("a.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf"))],
        ).status_code
        == 403
    )

    from fastapi.testclient import TestClient
    from app.main import app as fastapi_app

    bare = TestClient(fastapi_app)
    assert (
        bare.post(
            "/api/v1/ingestion/batch",
            files=[("files", ("a.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf"))],
        ).status_code
        == 401
    )

    mixed = client.post(
        "/api/v1/ingestion/batch",
        headers=_headers_for(operator.user),
        files=[
            ("files", ("good.pdf", io.BytesIO(b"%PDF-1.4 sample"), "application/pdf")),
            ("files", ("bad.exe", io.BytesIO(b"MZ"), "application/octet-stream")),
            ("files", ("also.pdf", io.BytesIO(b"%PDF-1.4 more"), "application/pdf")),
        ],
    )
    assert mixed.status_code == 200
    body = mixed.json()
    assert body["total"] == 3
    assert body["accepted"] == 2
    assert body["failed"] == 1
    assert any(item["status"] == "failed" for item in body["items"])
    assert all(
        item.get("processing_job_id")
        for item in body["items"]
        if item["status"] == "completed"
    )

    monkeypatch.setattr(settings, "INGESTION_MAX_BATCH_FILES", 2)
    too_many = client.post(
        "/api/v1/ingestion/batch",
        headers=_headers_for(operator.user),
        files=[
            ("files", ("1.pdf", io.BytesIO(b"%PDF-1.4 a"), "application/pdf")),
            ("files", ("2.pdf", io.BytesIO(b"%PDF-1.4 b"), "application/pdf")),
            ("files", ("3.pdf", io.BytesIO(b"%PDF-1.4 c"), "application/pdf")),
        ],
    )
    assert too_many.status_code == 400


def test_email_attachment_ingestion_and_duplicate(client, auth_client_factory):
    operator = auth_client_factory(
        username="ing_email_op",
        email="ing_email_op@example.com",
        password="OperatorPass2!",
        role=UserRole.OPERATOR.value,
    )
    fixture = MockEmailAttachmentProvider().fetch_attachments()[0]
    payload = {
        "provider": fixture.provider,
        "message_id": fixture.message_id,
        "sender": fixture.sender,
        "subject": fixture.subject,
        "received_at": fixture.received_at.isoformat(),
        "filename": fixture.filename,
        "content_base64": base64.b64encode(fixture.content).decode("ascii"),
        "content_type": fixture.content_type,
        "metadata": {"fixture": "step22", "password": "should-be-stripped", "api_key": "secret"},
    }

    first = client.post(
        "/api/v1/ingestion/email-attachments",
        headers=_headers_for(operator.user),
        json=payload,
    )
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["status"] == "completed"
    assert first_body["document_id"]
    assert first_body["processing_job_id"]
    assert first_body["already_ingested"] is False

    detail = client.get(
        f"/api/v1/ingestion/{first_body['ingestion_id']}",
        headers=_headers_for(operator.user),
    ).json()
    assert detail["metadata"]["sender"] == "vendor@example.test"
    assert detail["metadata"]["subject"] == "Invoice INV-2001"
    assert detail["metadata"]["message_id"] == "mock-message-001"
    assert "password" not in (detail["metadata"] or {})
    assert "api_key" not in (detail["metadata"] or {})

    db = client.testing_session_local()
    try:
        row = db.get(DocumentIngestion, uuid.UUID(str(first_body["ingestion_id"])))
        assert row is not None
        assert "password" not in (row.metadata_json or {})
        assert "%PDF" not in str(row.metadata_json)
    finally:
        db.close()

    second = client.post(
        "/api/v1/ingestion/email-attachments",
        headers=_headers_for(operator.user),
        json=payload,
    ).json()
    assert second["already_ingested"] is True
    assert second["status"] == "skipped"
    assert second["document_id"] == first_body["document_id"]

    other = dict(payload)
    other["filename"] = "invoice_2001_copy.pdf"
    other["content_base64"] = base64.b64encode(MOCK_INVOICE_PDF).decode("ascii")
    third = client.post(
        "/api/v1/ingestion/email-attachments",
        headers=_headers_for(operator.user),
        json=other,
    ).json()
    assert third["status"] == "completed"
    assert third["document_id"] != first_body["document_id"]

    other2 = dict(payload)
    other2["message_id"] = "mock-message-002"
    fourth = client.post(
        "/api/v1/ingestion/email-attachments",
        headers=_headers_for(operator.user),
        json=other2,
    ).json()
    assert fourth["status"] == "completed"

    listed = client.get("/api/v1/ingestion", headers=_headers_for(operator.user)).json()
    assert listed["total"] >= 3

    db = client.testing_session_local()
    try:
        audits = list(
            db.scalars(
                select(AuditLog).where(
                    AuditLog.action.in_(
                        [
                            "email_attachment_ingested",
                            "duplicate_email_attachment_skipped",
                            "document_ingested",
                        ]
                    )
                )
            ).all()
        )
        assert audits
        for entry in audits:
            blob = entry.details or ""
            assert "should-be-stripped" not in blob
            assert "%PDF" not in blob
    finally:
        db.close()


def test_ingestion_reuses_processing_jobs_no_duplicate_active(client, auth_client_factory):
    operator = auth_client_factory(
        username="ing_job_op",
        email="ing_job_op@example.com",
        password="OperatorPass3!",
        role=UserRole.OPERATOR.value,
    )
    response = client.post(
        "/api/v1/ingestion/batch",
        headers=_headers_for(operator.user),
        files=[("files", ("jobbed.pdf", io.BytesIO(b"%PDF-1.4 job"), "application/pdf"))],
    )
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["status"] == "completed"
    assert item["processing_job_id"]
    assert item["document_id"]

    db = client.testing_session_local()
    try:
        document_uuid = uuid.UUID(str(item["document_id"]))
        jobs = list(
            db.scalars(
                select(DocumentProcessingJob).where(
                    DocumentProcessingJob.document_id == document_uuid
                )
            ).all()
        )
        assert len(jobs) == 1
        assert str(jobs[0].id) == str(item["processing_job_id"])
        assert jobs[0].job_type == "document_processing"
        assert jobs[0].status in {
            ProcessingJobStatus.QUEUED.value,
            ProcessingJobStatus.RUNNING.value,
            ProcessingJobStatus.COMPLETED.value,
            ProcessingJobStatus.FAILED.value,
        }
        first_job_id = jobs[0].id
        first_status = jobs[0].status
    finally:
        db.close()

    process = client.post(
        f"/api/v1/documents/{item['document_id']}/process",
        headers=_headers_for(operator.user),
    )
    assert process.status_code == 200

    db = client.testing_session_local()
    try:
        document_uuid = uuid.UUID(str(item["document_id"]))
        all_jobs = list(
            db.scalars(
                select(DocumentProcessingJob).where(
                    DocumentProcessingJob.document_id == document_uuid
                )
            ).all()
        )
        active = [
            j
            for j in all_jobs
            if j.status
            in {ProcessingJobStatus.QUEUED.value, ProcessingJobStatus.RUNNING.value}
        ]
        assert len(active) <= 1
        if first_status in {
            ProcessingJobStatus.QUEUED.value,
            ProcessingJobStatus.RUNNING.value,
        }:
            assert process.json().get("job_id") == str(first_job_id)
        else:
            # Terminal first job → a new job may be created; still at most one active
            assert len(active) <= 1
    finally:
        db.close()


def test_reviewer_denied_ingestion(client, auth_client_factory):
    reviewer = auth_client_factory(
        username="ing_reviewer",
        email="ing_reviewer@example.com",
        password="ReviewerPass1!",
        role=UserRole.REVIEWER.value,
    )
    assert (
        client.post(
            "/api/v1/ingestion/batch",
            headers=_headers_for(reviewer.user),
            files=[("files", ("a.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf"))],
        ).status_code
        == 403
    )
