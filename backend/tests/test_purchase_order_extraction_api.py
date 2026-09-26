import io
import uuid

from tests.test_classification import UNKNOWN_TEXT, INVOICE_TEXT
from tests.test_purchase_order_extraction import COMPLETE_PO


def _upload_pdf(client, filename: str = "po.pdf"):
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


def test_process_po_extracts_structured_data(client, monkeypatch):
    document_id, response = _process_with_text(client, monkeypatch, COMPLETE_PO)

    assert response.status_code == 200
    payload = response.json()
    assert payload["document_type"] == "purchase_order"
    assert payload["has_purchase_order"] is True
    assert payload["purchase_order_id"] is not None

    po = client.get(f"/api/v1/documents/{document_id}/purchase-order")
    assert po.status_code == 200
    body = po.json()
    assert body["po_number"] == "PO-7788"
    assert body["vendor_name"] == "ABC Pvt Ltd"
    assert body["total_amount"] == 531000.0


def test_extract_po_endpoint_no_duplicates(client, monkeypatch):
    document_id, _ = _process_with_text(client, monkeypatch, COMPLETE_PO)
    first = client.post(f"/api/v1/documents/{document_id}/extract-po")
    second = client.post(f"/api/v1/documents/{document_id}/extract-po")
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]


def test_extract_po_rejects_non_po(client, monkeypatch):
    document_id, _ = _process_with_text(client, monkeypatch, UNKNOWN_TEXT)
    response = client.post(f"/api/v1/documents/{document_id}/extract-po")
    assert response.status_code == 400
    assert "purchase order" in response.json()["detail"].lower()


def test_extract_po_rejects_missing_text(client):
    created = _upload_pdf(client).json()
    response = client.post(f"/api/v1/documents/{created['id']}/extract-po")
    assert response.status_code == 400
    assert "extracted text" in response.json()["detail"].lower()


def test_extract_po_nonexistent(client):
    response = client.post(f"/api/v1/documents/{uuid.uuid4()}/extract-po")
    assert response.status_code == 404
