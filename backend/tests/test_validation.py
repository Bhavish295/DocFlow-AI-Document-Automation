import io
from datetime import datetime, timezone
from decimal import Decimal
import uuid

from app.models.document import Document, DocumentStatus
from app.models.invoice import Invoice
from app.models.purchase_order import PurchaseOrder
from app.services.validation_service import ValidationService
from tests.test_invoice_extraction import COMPLETE_INVOICE
from tests.test_purchase_order_extraction import COMPLETE_PO


def _upload_and_process(client, monkeypatch, text: str, filename: str):
    created = client.post(
        "/api/v1/documents",
        files={"file": (filename, io.BytesIO(b"%PDF-1.4 sample"), "application/pdf")},
    ).json()
    monkeypatch.setattr(
        "app.services.text_extraction.extract_selectable_pdf_text",
        lambda _path: text,
    )
    response = client.post(f"/api/v1/documents/{created['id']}/process")
    return response


def test_validation_fully_matching(client, monkeypatch):
    invoice_doc = _upload_and_process(client, monkeypatch, COMPLETE_INVOICE, "inv.pdf").json()
    po_doc = _upload_and_process(client, monkeypatch, COMPLETE_PO, "po.pdf").json()

    response = client.post(
        f"/api/v1/validations/invoice/{invoice_doc['invoice_id']}/purchase-order/{po_doc['purchase_order_id']}"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "matched"
    assert payload["vendor_match"] is True
    assert payload["currency_match"] is True
    assert payload["subtotal_match"] is True
    assert payload["tax_match"] is True
    assert payload["total_match"] is True
    assert payload["mismatch_summary"] is None


def test_validation_total_mismatch(client, monkeypatch):
    mismatched_invoice = COMPLETE_INVOICE.replace("Total: 531,000", "Total: 600,000")
    invoice_doc = _upload_and_process(client, monkeypatch, mismatched_invoice, "inv.pdf").json()
    po_doc = _upload_and_process(client, monkeypatch, COMPLETE_PO, "po.pdf").json()

    response = client.post(
        f"/api/v1/validations/invoice/{invoice_doc['invoice_id']}/purchase-order/{po_doc['purchase_order_id']}"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "mismatch"
    assert payload["total_match"] is False
    assert "Total mismatch" in payload["mismatch_summary"]


def test_validation_vendor_mismatch(client, monkeypatch):
    mismatched = COMPLETE_INVOICE.replace("ABC Pvt Ltd", "XYZ Supplies")
    invoice_doc = _upload_and_process(client, monkeypatch, mismatched, "inv.pdf").json()
    po_doc = _upload_and_process(client, monkeypatch, COMPLETE_PO, "po.pdf").json()

    response = client.post(
        f"/api/v1/validations/invoice/{invoice_doc['invoice_id']}/purchase-order/{po_doc['purchase_order_id']}"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "mismatch"
    assert payload["vendor_match"] is False
    assert "Vendor mismatch" in payload["mismatch_summary"]


def test_validation_currency_mismatch(client, monkeypatch):
    mismatched = COMPLETE_INVOICE.replace("Currency: PKR", "Currency: USD").replace(
        "Subtotal: 450,000", "Subtotal: USD 450,000"
    )
    invoice_doc = _upload_and_process(client, monkeypatch, mismatched, "inv.pdf").json()
    po_doc = _upload_and_process(client, monkeypatch, COMPLETE_PO, "po.pdf").json()

    response = client.post(
        f"/api/v1/validations/invoice/{invoice_doc['invoice_id']}/purchase-order/{po_doc['purchase_order_id']}"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "mismatch"
    assert payload["currency_match"] is False


def test_validation_subtotal_and_tax_mismatch(client, monkeypatch):
    mismatched = (
        COMPLETE_INVOICE.replace("Subtotal: 450,000", "Subtotal: 400,000")
        .replace("Tax: 81,000", "Tax: 50,000")
        .replace("Total: 531,000", "Total: 450,000")
    )
    invoice_doc = _upload_and_process(client, monkeypatch, mismatched, "inv.pdf").json()
    po_doc = _upload_and_process(client, monkeypatch, COMPLETE_PO, "po.pdf").json()

    response = client.post(
        f"/api/v1/validations/invoice/{invoice_doc['invoice_id']}/purchase-order/{po_doc['purchase_order_id']}"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "mismatch"
    assert payload["subtotal_match"] is False
    assert payload["tax_match"] is False
    assert "Subtotal mismatch" in payload["mismatch_summary"]
    assert "Tax mismatch" in payload["mismatch_summary"]


def test_validation_needs_review_for_missing_amount(client):
    db = client.testing_session_local()
    try:
        inv_doc = Document(
            id=uuid.uuid4(),
            original_filename="inv.pdf",
            stored_filename=f"{uuid.uuid4()}.pdf",
            file_type="pdf",
            file_size=10,
            storage_path="x",
            status=DocumentStatus.PROCESSED.value,
        )
        po_doc = Document(
            id=uuid.uuid4(),
            original_filename="po.pdf",
            stored_filename=f"{uuid.uuid4()}.pdf",
            file_type="pdf",
            file_size=10,
            storage_path="y",
            status=DocumentStatus.PROCESSED.value,
        )
        db.add_all([inv_doc, po_doc])
        db.flush()

        invoice = Invoice(
            id=uuid.uuid4(),
            document_id=inv_doc.id,
            vendor_name="ABC Traders",
            invoice_number="INV-1",
            subtotal=Decimal("100000.00"),
            tax_amount=Decimal("10000.00"),
            total_amount=Decimal("110000.00"),
            currency="PKR",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        purchase_order = PurchaseOrder(
            id=uuid.uuid4(),
            document_id=po_doc.id,
            vendor_name="ABC Traders",
            po_number="PO-1",
            subtotal=Decimal("100000.00"),
            tax_amount=Decimal("10000.00"),
            total_amount=None,
            currency="PKR",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add_all([invoice, purchase_order])
        db.commit()

        result = ValidationService(db).validate_invoice_against_po(invoice.id, purchase_order.id)
        assert result.status == "needs_review"
        assert result.total_match is None
        assert "Total needs review" in result.mismatch_summary
    finally:
        db.close()


def test_validation_amount_tolerance(client):
    db = client.testing_session_local()
    try:
        inv_doc = Document(
            id=uuid.uuid4(),
            original_filename="inv.pdf",
            stored_filename=f"{uuid.uuid4()}.pdf",
            file_type="pdf",
            file_size=10,
            storage_path="x",
            status=DocumentStatus.PROCESSED.value,
        )
        po_doc = Document(
            id=uuid.uuid4(),
            original_filename="po.pdf",
            stored_filename=f"{uuid.uuid4()}.pdf",
            file_type="pdf",
            file_size=10,
            storage_path="y",
            status=DocumentStatus.PROCESSED.value,
        )
        db.add_all([inv_doc, po_doc])
        db.flush()

        invoice = Invoice(
            id=uuid.uuid4(),
            document_id=inv_doc.id,
            vendor_name="ABC Traders",
            invoice_number="INV-1",
            subtotal=Decimal("100000.00"),
            tax_amount=Decimal("10000.00"),
            total_amount=Decimal("110000.00"),
            currency="PKR",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        purchase_order = PurchaseOrder(
            id=uuid.uuid4(),
            document_id=po_doc.id,
            vendor_name="ABC Traders",
            po_number="PO-1",
            subtotal=Decimal("100000.00"),
            tax_amount=Decimal("10000.00"),
            total_amount=Decimal("110000.005"),
            currency="Rs",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add_all([invoice, purchase_order])
        db.commit()

        result = ValidationService(db).validate_invoice_against_po(invoice.id, purchase_order.id)
        assert result.status == "matched"
        assert result.total_match is True
        assert result.currency_match is True
    finally:
        db.close()


def test_validation_no_duplicate_records(client, monkeypatch):
    invoice_doc = _upload_and_process(client, monkeypatch, COMPLETE_INVOICE, "inv.pdf").json()
    po_doc = _upload_and_process(client, monkeypatch, COMPLETE_PO, "po.pdf").json()
    path = (
        f"/api/v1/validations/invoice/{invoice_doc['invoice_id']}"
        f"/purchase-order/{po_doc['purchase_order_id']}"
    )

    first = client.post(path)
    second = client.post(path)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]

    listed = client.get("/api/v1/validations")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1


def test_get_validation(client, monkeypatch):
    invoice_doc = _upload_and_process(client, monkeypatch, COMPLETE_INVOICE, "inv.pdf").json()
    po_doc = _upload_and_process(client, monkeypatch, COMPLETE_PO, "po.pdf").json()
    created = client.post(
        f"/api/v1/validations/invoice/{invoice_doc['invoice_id']}/purchase-order/{po_doc['purchase_order_id']}"
    ).json()

    response = client.get(f"/api/v1/validations/{created['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]
