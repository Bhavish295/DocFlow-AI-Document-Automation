from decimal import Decimal

from app.services.line_item_extraction import RuleBasedLineItemExtractor
from app.services.quantity_matching import match_line_items, summarize_quantity_evidence
from app.models.document_line_item import DocumentLineItem
import uuid


INVOICE_LINES = """
ABC Pvt Ltd
Invoice No: INV-1
Item | Description | Qty | Unit Price | Total
SKU-1 | Laptop Stand | 10 | 100.00 | 1000.00
SKU-2 | USB Cable | 5 | 20.00 | 100.00
Subtotal: 1100.00
Tax: 110.00
Total: 1210.00
"""

PO_LINES = """
ABC Pvt Ltd
Purchase Order
PO Number: PO-1
Item | Description | Qty | Unit Price | Total
SKU-1 | Laptop Stand | 10 | 100.00 | 1000.00
SKU-2 | USB Cable | 5 | 20.00 | 100.00
Total: 1100.00
"""

GRN_LINES = """
GOODS RECEIPT NOTE
GRN Number: GRN-1
Supplier: ABC Pvt Ltd
PO Number: PO-1
Item | Description | Qty
SKU-1 | Laptop Stand | 10
SKU-2 | USB Cable | 5
"""


def test_extract_invoice_po_grn_line_items():
    extractor = RuleBasedLineItemExtractor()
    invoice_items = extractor.extract(INVOICE_LINES, document_type="invoice")
    po_items = extractor.extract(PO_LINES, document_type="purchase_order")
    grn_items = extractor.extract(GRN_LINES, document_type="goods_receipt")

    assert len(invoice_items) == 2
    assert invoice_items[0].item_code == "SKU-1"
    assert invoice_items[0].quantity == Decimal("10")
    assert invoice_items[0].quantity_type == "invoiced"
    assert po_items[0].quantity_type == "ordered"
    assert grn_items[0].quantity_type == "received"
    assert all(item.description for item in invoice_items)


def test_skip_totals_and_invalid_quantities():
    extractor = RuleBasedLineItemExtractor()
    text = """
Item | Description | Qty
SKU-9 | Widget | -3
Subtotal | 100
Tax | 10
Grand Total | 110
SKU-A | Good Item | 2
"""
    items = extractor.extract(text, document_type="invoice")
    assert len(items) == 1
    assert items[0].item_code == "SKU-A"
    assert items[0].quantity == Decimal("2")


def test_line_item_api_and_replace(client, monkeypatch):
    import io

    created = client.post(
        "/api/v1/documents",
        files={"file": ("lines.pdf", io.BytesIO(b"%PDF-1.4 sample"), "application/pdf")},
    ).json()
    monkeypatch.setattr(
        "app.services.text_extraction.extract_selectable_pdf_text",
        lambda _path: INVOICE_LINES,
    )
    processed = client.post(f"/api/v1/documents/{created['id']}/process")
    assert processed.status_code == 200
    assert processed.json()["document_type"] == "invoice"

    listed = client.get(f"/api/v1/documents/{created['id']}/line-items")
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] == 2
    first_ids = [item["id"] for item in body["items"]]

    again = client.post(f"/api/v1/documents/{created['id']}/extract-line-items")
    assert again.status_code == 200
    assert again.json()["total"] == 2
    second_ids = [item["id"] for item in again.json()["items"]]
    assert first_ids != second_ids


def test_quantity_matching_rules():
    def fake(code: str, desc: str, qty: float) -> DocumentLineItem:
        return DocumentLineItem(
            id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            line_number=1,
            item_code=code,
            description=desc,
            quantity=Decimal(str(qty)),
        )

    po = [fake("SKU-1", "Laptop", 10), fake("SKU-2", "Mouse", 20)]
    grn = [fake("SKU-1", "Laptop", 10), fake("SKU-2", "Mouse", 20)]
    inv = [fake("SKU-1", "Laptop", 10), fake("SKU-2", "Mouse", 20)]
    evidence = match_line_items(po, grn, inv)
    status, *_rest = summarize_quantity_evidence(evidence)
    assert status == "matched"

    mismatch_inv = [fake("SKU-1", "Laptop", 12), fake("SKU-2", "Mouse", 20)]
    evidence2 = match_line_items(po, grn, mismatch_inv)
    status2, detail2, *_ = summarize_quantity_evidence(evidence2)
    assert status2 == "mismatch"
    assert "exceeds" in (detail2 or "").lower() or "mismatch" in (detail2 or "").lower()

    ambiguous = match_line_items(
        [fake(None, "Generic Cable", 5)],
        [fake(None, "Other Widget", 5)],
        [fake(None, "Generic Cable", 5)],
    )
    status3, *_ = summarize_quantity_evidence(ambiguous)
    assert status3 == "needs_review"
