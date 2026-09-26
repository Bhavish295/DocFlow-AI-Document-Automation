import io
import uuid

from tests.test_classification import UNKNOWN_TEXT
from tests.test_invoice_extraction import COMPLETE_INVOICE


def _upload_pdf(client, filename: str = "invoice.pdf"):
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


def test_process_invoice_extracts_structured_data(client, monkeypatch):
    document_id, response = _process_with_text(client, monkeypatch, COMPLETE_INVOICE)

    assert response.status_code == 200
    payload = response.json()
    assert payload["document_type"] == "invoice"
    assert payload["has_invoice"] is True

    invoice = client.get(f"/api/v1/documents/{document_id}/invoice")
    assert invoice.status_code == 200
    body = invoice.json()
    assert body["vendor_name"] == "ABC Pvt Ltd"
    assert body["invoice_number"] == "INV-1827"
    assert body["currency"] == "PKR"
    assert body["total_amount"] == 531000.0


def test_extract_endpoint_and_no_duplicates(client, monkeypatch):
    document_id, _ = _process_with_text(client, monkeypatch, COMPLETE_INVOICE)

    first = client.post(f"/api/v1/documents/{document_id}/extract")
    second = client.post(f"/api/v1/documents/{document_id}/extract")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["invoice_number"] == "INV-1827"


def test_extract_rejects_non_invoice(client, monkeypatch):
    document_id, process_response = _process_with_text(client, monkeypatch, UNKNOWN_TEXT)
    assert process_response.json()["document_type"] == "other"

    response = client.post(f"/api/v1/documents/{document_id}/extract")

    assert response.status_code == 400
    assert "invoice" in response.json()["detail"].lower()


def test_extract_rejects_missing_text(client):
    created = _upload_pdf(client).json()

    response = client.post(f"/api/v1/documents/{created['id']}/extract")

    assert response.status_code == 400
    assert "extracted text" in response.json()["detail"].lower()


def test_get_invoice_unavailable(client, monkeypatch):
    document_id, _ = _process_with_text(client, monkeypatch, UNKNOWN_TEXT)

    response = client.get(f"/api/v1/documents/{document_id}/invoice")

    assert response.status_code == 404


def test_extract_nonexistent_document(client):
    response = client.post(f"/api/v1/documents/{uuid.uuid4()}/extract")
    assert response.status_code == 404
