import io
import uuid

from sqlalchemy import func, select

from app.models.vendor import Vendor
from tests.test_invoice_extraction import COMPLETE_INVOICE
from tests.test_purchase_order_extraction import COMPLETE_PO


def _upload_pdf(client, filename: str = "doc.pdf"):
    return client.post(
        "/api/v1/documents",
        files={"file": (filename, io.BytesIO(b"%PDF-1.4 sample"), "application/pdf")},
    )


def _process_with_text(client, monkeypatch, text: str, filename: str = "doc.pdf"):
    created = _upload_pdf(client, filename=filename).json()
    monkeypatch.setattr(
        "app.services.text_extraction.extract_selectable_pdf_text",
        lambda _path: text,
    )
    response = client.post(f"/api/v1/documents/{created['id']}/process")
    return created["id"], response


def test_list_create_get_update_delete_vendor(client):
    create = client.post(
        "/api/v1/vendors",
        json={
            "name": "Manual Vendor Co",
            "email": "ops@manual.example",
            "phone": "03001234567",
            "tax_id": "TAX-100",
        },
    )
    assert create.status_code == 201
    vendor = create.json()
    assert vendor["name"] == "Manual Vendor Co"
    assert vendor["summary"]["invoice_count"] == 0

    listed = client.get("/api/v1/vendors")
    assert listed.status_code == 200
    assert listed.json()["total"] >= 1
    assert any(item["id"] == vendor["id"] for item in listed.json()["items"])

    detail = client.get(f"/api/v1/vendors/{vendor['id']}")
    assert detail.status_code == 200
    assert detail.json()["normalized_name"] == "manual vendor co"

    updated = client.patch(
        f"/api/v1/vendors/{vendor['id']}",
        json={"phone": "03007654321", "address": "Karachi"},
    )
    assert updated.status_code == 200
    assert updated.json()["phone"] == "03007654321"
    assert updated.json()["address"] == "Karachi"

    deleted = client.delete(f"/api/v1/vendors/{vendor['id']}")
    assert deleted.status_code == 200

    missing = client.get(f"/api/v1/vendors/{vendor['id']}")
    assert missing.status_code == 404


def test_invalid_vendor_id_returns_404(client):
    response = client.get(f"/api/v1/vendors/{uuid.uuid4()}")
    assert response.status_code == 404


def test_invoice_and_po_link_same_vendor_without_duplicates(client, monkeypatch):
    invoice_doc_id, invoice_process = _process_with_text(
        client,
        monkeypatch,
        COMPLETE_INVOICE,
        filename="invoice.pdf",
    )
    assert invoice_process.status_code == 200

    invoice = client.get(f"/api/v1/documents/{invoice_doc_id}/invoice").json()
    assert invoice["vendor_name"] == "ABC Pvt Ltd"
    assert invoice["vendor_id"] is not None

    second_text = COMPLETE_INVOICE.replace("ABC Pvt Ltd", "ABC PVT LTD")
    second_doc_id, second_process = _process_with_text(
        client,
        monkeypatch,
        second_text,
        filename="invoice-2.pdf",
    )
    assert second_process.status_code == 200
    second_invoice = client.get(f"/api/v1/documents/{second_doc_id}/invoice").json()
    assert second_invoice["vendor_id"] == invoice["vendor_id"]

    po_doc_id, po_process = _process_with_text(
        client,
        monkeypatch,
        COMPLETE_PO,
        filename="po.pdf",
    )
    assert po_process.status_code == 200
    purchase_order = client.get(f"/api/v1/documents/{po_doc_id}/purchase-order").json()
    assert purchase_order["vendor_name"] == "ABC Pvt Ltd"
    assert purchase_order["vendor_id"] == invoice["vendor_id"]

    db = client.testing_session_local()
    try:
        vendor_count = db.scalar(select(func.count()).select_from(Vendor)) or 0
        assert vendor_count == 1
    finally:
        db.close()

    detail = client.get(f"/api/v1/vendors/{invoice['vendor_id']}").json()
    assert detail["summary"]["invoice_count"] == 2
    assert detail["summary"]["purchase_order_count"] == 1


def test_unsafe_delete_vendor_blocked(client, monkeypatch):
    document_id, process_response = _process_with_text(
        client,
        monkeypatch,
        COMPLETE_INVOICE,
        filename="blocked.pdf",
    )
    assert process_response.status_code == 200
    invoice = client.get(f"/api/v1/documents/{document_id}/invoice").json()
    assert invoice["vendor_id"]

    response = client.delete(f"/api/v1/vendors/{invoice['vendor_id']}")
    assert response.status_code == 409
    assert "linked" in response.json()["detail"].lower()


def test_duplicate_manual_create_rejected(client):
    first = client.post("/api/v1/vendors", json={"name": "Unique Supplies"})
    assert first.status_code == 201

    second = client.post("/api/v1/vendors", json={"name": " unique supplies "})
    assert second.status_code == 409
