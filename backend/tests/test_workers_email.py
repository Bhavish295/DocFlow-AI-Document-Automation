"""Step 27 — Celery workers and email ingestion tests (mocked; no real Redis/IMAP)."""

from __future__ import annotations

from datetime import datetime, timezone
from email.message import EmailMessage
import io
import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.core.config import settings
from app.core.security import create_access_token
from app.models.user import UserRole
from app.services.email_attachment_provider import (
    NormalizedEmailAttachment,
    build_email_source_identity,
)
from app.services.email_polling_service import (
    EmailPollingService,
    reset_email_poll_status_for_tests,
)
from app.services.imap_email_provider import ImapEmailAttachmentProvider, get_email_attachment_provider
from app.services.mock_email_provider import MOCK_INVOICE_PDF, MockEmailAttachmentProvider
from app.services.processing_dispatch import enqueue_processing_job
from app.workers.tasks import _is_transient_error, process_document_job


def _headers_for(user) -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject=user.id, role=user.role)}"}


@pytest.fixture(autouse=True)
def _reset_email_status(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "uploads"))
    reset_email_poll_status_for_tests()
    yield
    reset_email_poll_status_for_tests()


def test_redis_url_and_worker_mode_config():
    assert settings.REDIS_URL
    assert settings.processing_worker_mode in {"local", "celery"}
    assert isinstance(settings.uses_celery_workers, bool)


def test_celery_task_is_registered():
    assert process_document_job.name == "app.workers.tasks.process_document_job"
    assert process_document_job.max_retries >= 1


def test_local_worker_mode_dispatch(monkeypatch):
    monkeypatch.setattr(settings, "PROCESSING_WORKER_MODE", "local")
    monkeypatch.setattr(settings, "DOCUMENT_PROCESSING_SYNC", False)
    called = {}

    def fake_execute(job_id):
        called["id"] = job_id

    bg = MagicMock()
    with patch("app.services.processing_dispatch.execute_processing_job", fake_execute):
        mode = enqueue_processing_job(uuid.uuid4(), background_tasks=bg, force_sync=False)
    assert mode == "local"
    assert bg.add_task.called


def test_celery_worker_mode_dispatch(monkeypatch):
    monkeypatch.setattr(settings, "PROCESSING_WORKER_MODE", "celery")
    monkeypatch.setattr(settings, "DOCUMENT_PROCESSING_SYNC", False)
    job_id = uuid.uuid4()
    with patch("app.workers.tasks.process_document_job.delay") as delay:
        mode = enqueue_processing_job(job_id, background_tasks=None, force_sync=False)
    assert mode == "celery"
    delay.assert_called_once_with(str(job_id))


def test_processing_task_runs_existing_pipeline(monkeypatch):
    monkeypatch.setattr(settings, "CELERY_TASK_MAX_RETRIES", 2)
    job_id = str(uuid.uuid4())
    with patch("app.services.document_processing_runner.execute_processing_job") as execute:
        result = process_document_job.run(job_id)
    execute.assert_called_once()
    assert result["job_id"] == job_id


def test_processing_task_retries_transient_failures(monkeypatch):
    monkeypatch.setattr(settings, "CELERY_TASK_MAX_RETRIES", 2)
    monkeypatch.setattr(settings, "CELERY_TASK_RETRY_DELAY_SECONDS", 1)

    class RetryExc(Exception):
        pass

    task = process_document_job
    with patch(
        "app.services.document_processing_runner.execute_processing_job",
        side_effect=ConnectionError("connection refused"),
    ):
        with patch.object(task, "retry", side_effect=RetryExc("retried")) as retry:
            try:
                task.run(str(uuid.uuid4()))
                assert False, "expected retry"
            except RetryExc:
                pass
            assert retry.called


def test_transient_error_detection():
    assert _is_transient_error(ConnectionError("connection refused"))
    assert not _is_transient_error(ValueError("bad pdf"))


def test_imap_not_configured():
    provider = ImapEmailAttachmentProvider(host="", username="", password="")
    try:
        provider.fetch_attachments()
        assert False
    except Exception as exc:
        assert "not configured" in str(exc).lower()


def test_get_provider_none(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "none")
    assert get_email_attachment_provider() is None


def test_imap_normalization_from_message(monkeypatch):
    msg = EmailMessage()
    msg["From"] = "vendor@example.test"
    msg["Subject"] = "PO files"
    msg["Message-ID"] = "<abc-123@example.test>"
    msg["Date"] = "Tue, 24 Mar 2026 10:00:00 +0000"
    msg.set_content("see attachments")
    msg.add_attachment(
        MOCK_INVOICE_PDF,
        maintype="application",
        subtype="pdf",
        filename="invoice.pdf",
    )
    msg.add_attachment(
        b"not-allowed",
        maintype="application",
        subtype="octet-stream",
        filename="malware.exe",
    )
    raw = msg.as_bytes()

    fake_client = MagicMock()
    fake_client.fetch.return_value = ("OK", [(b"1 (RFC822)", raw)])

    provider = ImapEmailAttachmentProvider(
        host="imap.example.test",
        username="user",
        password="secret",
    )
    attachments = provider._attachments_from_message(fake_client, b"1")
    assert len(attachments) == 1
    assert attachments[0].filename == "invoice.pdf"
    assert attachments[0].message_id == "abc-123@example.test"
    assert attachments[0].provider == "imap"
    assert "password" not in str(attachments[0].metadata).lower()


def test_email_poll_disabled(client, monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "none")
    response = client.get("/api/v1/ingestion/email/status")
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "none"
    assert body["configured"] is False
    assert "password" not in response.text.lower()


def test_email_poll_missing_imap_config(client, monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "imap")
    monkeypatch.setattr(settings, "EMAIL_IMAP_HOST", "")
    monkeypatch.setattr(settings, "EMAIL_IMAP_USERNAME", "")
    monkeypatch.setattr(settings, "EMAIL_IMAP_PASSWORD", "")
    response = client.post("/api/v1/ingestion/email/poll")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"not_configured", "disabled", "error"}
    assert body["configured"] is False


def test_email_poll_rbac(client, auth_client_factory, monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "mock")
    viewer = auth_client_factory(
        username="email_viewer",
        email="email_viewer@example.com",
        password="ViewerPass1!",
        role=UserRole.VIEWER.value,
    )
    assert (
        client.post(
            "/api/v1/ingestion/email/poll",
            headers=_headers_for(viewer.user),
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/api/v1/ingestion/email/status",
            headers=_headers_for(viewer.user),
        ).status_code
        == 200
    )


def test_email_poll_mock_supported_and_duplicate(client, monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "mock")
    monkeypatch.setattr(settings, "DOCUMENT_PROCESSING_SYNC", True)
    first = client.post("/api/v1/ingestion/email/poll")
    assert first.status_code == 200
    body = first.json()
    assert body["status"] == "ok"
    assert body["processed"] >= 1
    assert "password" not in first.text.lower()

    second = client.post("/api/v1/ingestion/email/poll")
    assert second.status_code == 200
    assert second.json()["skipped"] >= 1


def test_multiple_attachments_and_one_failure_continues(client, monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "mock")
    monkeypatch.setattr(settings, "DOCUMENT_PROCESSING_SYNC", True)

    good = NormalizedEmailAttachment(
        provider="mock",
        message_id="multi-1",
        sender="a@test",
        subject="ok",
        received_at=datetime.now(timezone.utc),
        filename="good.pdf",
        content=MOCK_INVOICE_PDF,
        content_type="application/pdf",
    )
    also_good = NormalizedEmailAttachment(
        provider="mock",
        message_id="multi-1",
        sender="a@test",
        subject="ok",
        received_at=datetime.now(timezone.utc),
        filename="second.pdf",
        content=MOCK_INVOICE_PDF + b"\n",
        content_type="application/pdf",
    )

    class FlakyProvider:
        def fetch_attachments(self):
            return [good, also_good]

    monkeypatch.setattr(
        "app.services.email_polling_service.get_email_attachment_provider",
        lambda: FlakyProvider(),
    )

    original = EmailPollingService._ingest_one
    calls = {"n": 0}

    def flaky(self, attachment, **kwargs):
        calls["n"] += 1
        if attachment.filename == "good.pdf":
            raise RuntimeError("boom")
        return original(self, attachment, **kwargs)

    monkeypatch.setattr(EmailPollingService, "_ingest_one", flaky)
    result = client.post("/api/v1/ingestion/email/poll").json()
    assert result["status"] == "ok"
    assert result["failed"] >= 1
    assert result["processed"] >= 1


def test_credentials_never_in_status(client, monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "imap")
    monkeypatch.setattr(settings, "EMAIL_IMAP_HOST", "imap.example.test")
    monkeypatch.setattr(settings, "EMAIL_IMAP_USERNAME", "mailuser")
    monkeypatch.setattr(settings, "EMAIL_IMAP_PASSWORD", "super-secret-password")
    response = client.get("/api/v1/ingestion/email/status")
    text = response.text.lower()
    assert "super-secret-password" not in text
    assert "mailuser" not in text


def test_source_identity_duplicate_key():
    key = build_email_source_identity(
        provider="imap",
        message_id="abc",
        filename="Invoice.PDF",
    )
    assert key == "imap:abc:invoice.pdf"


def test_existing_processing_still_works(client, monkeypatch):
    monkeypatch.setattr(settings, "DOCUMENT_PROCESSING_SYNC", True)
    monkeypatch.setattr(settings, "PROCESSING_WORKER_MODE", "local")
    upload = client.post(
        "/api/v1/documents",
        files={"file": ("job.pdf", io.BytesIO(b"%PDF-1.4 worker"), "application/pdf")},
    )
    assert upload.status_code == 201
    doc_id = upload.json()["id"]
    processed = client.post(f"/api/v1/documents/{doc_id}/process")
    assert processed.status_code == 200
    assert processed.json()["job_id"]
