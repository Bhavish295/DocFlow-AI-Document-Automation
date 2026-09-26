import io

from app.core.config import settings


INVOICE_TEXT = """
ABC Pvt Ltd
Invoice No: INV-JOB-1
Date: 10-09-2026
Item | Description | Qty | Unit Price | Total
SKU-1 | Widget | 2 | 10.00 | 20.00
Subtotal: 20.00
Tax: 2.00
Total: 22.00
Currency: PKR
"""


def _upload(client, name="job.pdf"):
    return client.post(
        "/api/v1/documents",
        files={"file": (name, io.BytesIO(b"%PDF-1.4 sample"), "application/pdf")},
    ).json()


def _process(client, monkeypatch, document_id, text=INVOICE_TEXT):
    monkeypatch.setattr(
        "app.services.text_extraction.extract_selectable_pdf_text",
        lambda _path: text,
    )
    return client.post(f"/api/v1/documents/{document_id}/process")


def test_process_creates_job_and_completes(client, monkeypatch):
    created = _upload(client)
    response = _process(client, monkeypatch, created["id"])
    assert response.status_code == 200
    body = response.json()
    assert body["job_id"]
    assert body["job_status"] == "completed"
    assert body["progress"] == 100
    assert body["current_stage"] == "completed"
    assert body["status"] == "processed"
    assert body["document_type"] == "invoice"

    job = client.get(f"/api/v1/processing-jobs/{body['job_id']}")
    assert job.status_code == 200
    assert job.json()["status"] == "completed"
    assert job.json()["progress"] == 100


def test_duplicate_active_job_returns_existing(client, monkeypatch):
    other = _upload(client, "active.pdf")
    monkeypatch.setattr(
        "app.services.document_processing_orchestrator.DocumentProcessingRunner.run",
        lambda self, job_id: None,
    )
    monkeypatch.setattr(settings, "DOCUMENT_PROCESSING_SYNC", True)

    queued = client.post(f"/api/v1/documents/{other['id']}/process")
    assert queued.status_code == 200
    job_id = queued.json()["job_id"]
    assert queued.json()["job_status"] == "queued"

    again = client.post(f"/api/v1/documents/{other['id']}/process")
    assert again.status_code == 200
    assert again.json()["job_id"] == job_id


def test_failure_marks_job_failed(client, monkeypatch):
    created = _upload(client, "fail.pdf")
    monkeypatch.setattr(
        "app.services.text_extraction.extract_selectable_pdf_text",
        lambda _path: "",
    )
    monkeypatch.setattr(
        "app.services.text_extraction.ocr_pdf_pages",
        lambda _path: "",
    )
    response = client.post(f"/api/v1/documents/{created['id']}/process")
    assert response.status_code == 200
    body = response.json()
    assert body["job_status"] == "failed"
    assert body["status"] == "failed"
    assert body["job_id"]
    job = client.get(f"/api/v1/processing-jobs/{body['job_id']}").json()
    assert job["status"] == "failed"
    assert job["error_message"]
    assert "Traceback" not in (job["error_message"] or "")


def test_retry_failed_job(client, monkeypatch):
    created = _upload(client, "retry.pdf")
    monkeypatch.setattr(
        "app.services.text_extraction.extract_selectable_pdf_text",
        lambda _path: "",
    )
    monkeypatch.setattr(
        "app.services.text_extraction.ocr_pdf_pages",
        lambda _path: "",
    )
    failed = client.post(f"/api/v1/documents/{created['id']}/process").json()
    assert failed["job_status"] == "failed"
    failed_id = failed["job_id"]

    monkeypatch.setattr(
        "app.services.text_extraction.extract_selectable_pdf_text",
        lambda _path: INVOICE_TEXT,
    )
    retried = client.post(f"/api/v1/processing-jobs/{failed_id}/retry")
    assert retried.status_code == 200
    body = retried.json()
    assert body["id"] != failed_id
    assert body["parent_job_id"] == failed_id
    assert body["status"] == "completed"

    bad = client.post(f"/api/v1/processing-jobs/{body['id']}/retry")
    assert bad.status_code == 400


def test_cancel_queued_and_reject_completed(client, monkeypatch):
    created = _upload(client, "cancel.pdf")
    monkeypatch.setattr(settings, "DOCUMENT_PROCESSING_SYNC", True)

    with monkeypatch.context() as patch:
        patch.setattr(
            "app.services.document_processing_orchestrator.DocumentProcessingRunner.run",
            lambda self, job_id: None,
        )
        queued = client.post(f"/api/v1/documents/{created['id']}/process").json()
        assert queued["job_status"] == "queued"
        cancelled = client.post(f"/api/v1/processing-jobs/{queued['job_id']}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"

    other = _upload(client, "done.pdf")
    monkeypatch.setattr(
        "app.services.text_extraction.extract_selectable_pdf_text",
        lambda _path: INVOICE_TEXT,
    )
    done = client.post(f"/api/v1/documents/{other['id']}/process").json()
    assert done["job_status"] == "completed"
    reject = client.post(f"/api/v1/processing-jobs/{done['job_id']}/cancel")
    assert reject.status_code == 400


def test_job_history_preserves_completed(client, monkeypatch):
    created = _upload(client, "hist.pdf")
    first = _process(client, monkeypatch, created["id"]).json()
    assert first["job_status"] == "completed"

    monkeypatch.setattr(
        "app.services.text_extraction.extract_selectable_pdf_text",
        lambda _path: "",
    )
    monkeypatch.setattr(
        "app.services.text_extraction.ocr_pdf_pages",
        lambda _path: "",
    )
    second = client.post(f"/api/v1/documents/{created['id']}/process").json()
    assert second["job_status"] == "failed"

    history = client.get(f"/api/v1/documents/{created['id']}/processing-jobs").json()
    assert history["total"] >= 2
    statuses = {item["status"] for item in history["items"]}
    assert "completed" in statuses
    assert "failed" in statuses


def test_stage_progress_values():
    from app.models.document_processing_job import STAGE_PROGRESS, ProcessingJobStage

    assert STAGE_PROGRESS[ProcessingJobStage.QUEUED.value] == 0
    assert STAGE_PROGRESS[ProcessingJobStage.TEXT_EXTRACTION.value] == 20
    assert STAGE_PROGRESS[ProcessingJobStage.CLASSIFICATION.value] == 40
    assert STAGE_PROGRESS[ProcessingJobStage.STRUCTURED_EXTRACTION.value] == 60
    assert STAGE_PROGRESS[ProcessingJobStage.LINE_ITEMS.value] == 80
    assert STAGE_PROGRESS[ProcessingJobStage.COMPLETED.value] == 100
