import io
import uuid

from tests.test_classification import INVOICE_TEXT, UNKNOWN_TEXT


def _upload_pdf(client, filename: str = "doc.pdf"):
    return client.post(
        "/api/v1/documents",
        files={"file": (filename, io.BytesIO(b"%PDF-1.4 sample"), "application/pdf")},
    )


def _process_with_text(client, monkeypatch, text: str):
    created = _upload_pdf(client).json()
    monkeypatch.setattr(
        "app.services.text_extraction.extract_selectable_pdf_text",
        lambda _path: text,
    )
    response = client.post(f"/api/v1/documents/{created['id']}/process")
    return created["id"], response


def test_classify_unprocessed_document(client):
    created = _upload_pdf(client).json()

    response = client.post(f"/api/v1/documents/{created['id']}/classify")

    assert response.status_code == 400
    assert "processed" in response.json()["detail"].lower()


def test_get_classification_unprocessed_document(client):
    created = _upload_pdf(client).json()

    response = client.get(f"/api/v1/documents/{created['id']}/classification")

    assert response.status_code == 400
    assert "processed" in response.json()["detail"].lower()


def test_process_extracts_text_and_classifies(client, monkeypatch):
    document_id, response = _process_with_text(client, monkeypatch, INVOICE_TEXT)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "processed"
    assert payload["document_type"] == "invoice"
    assert payload["classification_confidence"] is not None
    assert payload["classification_confidence"] >= 0.55

    classification = client.get(f"/api/v1/documents/{document_id}/classification")
    assert classification.status_code == 200
    body = classification.json()
    assert body["document_type"] == "invoice"
    assert body["confidence"] == payload["classification_confidence"]
    assert body["status"] == "processed"


def test_manual_classify_endpoint(client, monkeypatch):
    document_id, process_response = _process_with_text(client, monkeypatch, UNKNOWN_TEXT)
    assert process_response.status_code == 200
    assert process_response.json()["document_type"] == "other"

    classify_response = client.post(f"/api/v1/documents/{document_id}/classify")

    assert classify_response.status_code == 200
    assert classify_response.json()["document_type"] == "other"
    assert classify_response.json()["classification_confidence"] is not None


def test_classify_nonexistent_document_returns_404(client):
    response = client.post(f"/api/v1/documents/{uuid.uuid4()}/classify")
    assert response.status_code == 404
