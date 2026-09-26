import io

from app.models.document_review import ReviewReason


MATCHED_INVOICE = """
ABC Pvt Ltd
Invoice No: INV-9001
Date: 10-09-2026
PO Number: PO-1007
GRN Number: GRN-501
Item | Description | Qty | Unit Price | Total
SKU-1 | Laptop | 10 | 45000 | 450000
SKU-2 | Mouse | 20 | 50 | 1000
Subtotal: 450,000
Tax: 81,000
Total: 531,000
Currency: PKR
"""

MATCHED_PO = """
ABC Pvt Ltd
Purchase Order
PO Number: PO-1007
PO Date: 01-09-2026
Item | Description | Qty | Unit Price | Total
SKU-1 | Laptop | 10 | 45000 | 450000
SKU-2 | Mouse | 20 | 50 | 1000
Subtotal: 450,000
Tax: 81,000
Total: 531,000
Currency: PKR
"""

MATCHED_GRN = """
GOODS RECEIPT NOTE
GRN Number: GRN-501
Supplier: ABC Pvt Ltd
PO Number: PO-1007
Received Date: 12 March 2026
Item | Description | Qty
SKU-1 | Laptop | 10
SKU-2 | Mouse | 20
Quantity Received: 30
"""


def _upload_process(client, monkeypatch, filename: str, text: str):
    created = client.post(
        "/api/v1/documents",
        files={"file": (filename, io.BytesIO(b"%PDF-1.4 sample"), "application/pdf")},
    ).json()
    monkeypatch.setattr(
        "app.services.text_extraction.extract_selectable_pdf_text",
        lambda _path: text,
    )
    processed = client.post(f"/api/v1/documents/{created['id']}/process")
    assert processed.status_code == 200
    return processed.json()


def _clear_active_reviews(client, document_id: str):
    reviews = client.get("/api/v1/reviews").json()
    for item in reviews["items"]:
        if item["document_id"] != document_id:
            continue
        if item["status"] not in {"pending", "in_review"}:
            continue
        started = client.post(f"/api/v1/reviews/{item['id']}/start")
        assert started.status_code == 200
        approved = client.post(f"/api/v1/reviews/{item['id']}/approve")
        assert approved.status_code == 200


def _confirm_relationships(client, invoice, po, grn):
    for payload in (
        {
            "source_document_id": invoice["id"],
            "target_document_id": po["id"],
            "relationship_type": "invoice_purchase_order",
            "match_key": "PO-1007",
        },
        {
            "source_document_id": grn["id"],
            "target_document_id": po["id"],
            "relationship_type": "goods_receipt_purchase_order",
            "match_key": "PO-1007",
        },
        {
            "source_document_id": invoice["id"],
            "target_document_id": grn["id"],
            "relationship_type": "invoice_goods_receipt",
            "match_key": "GRN-501",
        },
    ):
        response = client.post("/api/v1/document-relationships", json=payload)
        assert response.status_code == 201


def _run_three_way(client, invoice, po, grn):
    return client.post(
        "/api/v1/validations/three-way",
        json={
            "invoice_document_id": invoice["id"],
            "purchase_order_document_id": po["id"],
            "goods_receipt_document_id": grn["id"],
        },
    )


def test_three_way_matched_case(client, monkeypatch):
    invoice = _upload_process(client, monkeypatch, "inv.pdf", MATCHED_INVOICE)
    po = _upload_process(client, monkeypatch, "po.pdf", MATCHED_PO)
    grn = _upload_process(client, monkeypatch, "grn.pdf", MATCHED_GRN)
    _confirm_relationships(client, invoice, po, grn)
    _clear_active_reviews(client, invoice["id"])

    first = _run_three_way(client, invoice, po, grn)
    assert first.status_code == 200
    body = first.json()
    assert body["status"] == "matched"
    assert body["vendor_status"] == "matched"
    assert body["po_reference_status"] == "matched"
    assert body["grn_reference_status"] == "matched"
    assert body["financial_status"] == "matched"
    assert body["relationship_status"] == "matched"
    assert body["quantity_status"] == "matched"
    assert 0.0 <= body["overall_confidence"] <= 1.0
    assert body["quantity_evidence"]
    assert all(item["status"] == "matched" for item in body["quantity_evidence"])

    reviews = client.get(
        "/api/v1/reviews",
        params={"reason": ReviewReason.THREE_WAY_MATCH_MISMATCH.value},
    ).json()
    assert reviews["total"] == 0
    reviews_nr = client.get(
        "/api/v1/reviews",
        params={"reason": ReviewReason.THREE_WAY_MATCH_NEEDS_REVIEW.value},
    ).json()
    assert reviews_nr["total"] == 0

    second = _run_three_way(client, invoice, po, grn)
    assert second.status_code == 200
    assert second.json()["id"] == body["id"]

    listed = client.get("/api/v1/validations/three-way")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    fetched = client.get(f"/api/v1/validations/three-way/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "matched"


def test_vendor_mismatch_precedence(client, monkeypatch):
    invoice = _upload_process(client, monkeypatch, "inv2.pdf", MATCHED_INVOICE)
    po = _upload_process(
        client,
        monkeypatch,
        "po2.pdf",
        MATCHED_PO.replace("ABC Pvt Ltd", "XYZ Traders", 1),
    )
    grn = _upload_process(client, monkeypatch, "grn2.pdf", MATCHED_GRN)
    _confirm_relationships(client, invoice, po, grn)
    _clear_active_reviews(client, invoice["id"])

    result = _run_three_way(client, invoice, po, grn).json()
    assert result["status"] == "mismatch"
    assert result["vendor_status"] == "mismatch"
    assert any("Vendor" in item for item in result["mismatched_fields"])

    reviews = client.get(
        "/api/v1/reviews",
        params={"reason": ReviewReason.THREE_WAY_MATCH_MISMATCH.value},
    ).json()
    assert reviews["total"] == 1


def test_po_and_grn_reference_mismatches(client, monkeypatch):
    invoice = _upload_process(client, monkeypatch, "inv3.pdf", MATCHED_INVOICE)
    po = _upload_process(
        client,
        monkeypatch,
        "po3.pdf",
        MATCHED_PO.replace("PO-1007", "PO-9999"),
    )
    grn = _upload_process(client, monkeypatch, "grn3.pdf", MATCHED_GRN)
    _confirm_relationships(client, invoice, po, grn)
    po_result = _run_three_way(client, invoice, po, grn).json()
    assert po_result["status"] == "mismatch"
    assert po_result["po_reference_status"] == "mismatch"

    invoice_b = _upload_process(
        client,
        monkeypatch,
        "inv4.pdf",
        MATCHED_INVOICE.replace("GRN-501", "GRN-777"),
    )
    po_b = _upload_process(client, monkeypatch, "po4.pdf", MATCHED_PO)
    grn_b = _upload_process(client, monkeypatch, "grn4.pdf", MATCHED_GRN)
    _confirm_relationships(client, invoice_b, po_b, grn_b)
    grn_result = _run_three_way(client, invoice_b, po_b, grn_b).json()
    assert grn_result["status"] == "mismatch"
    assert grn_result["grn_reference_status"] == "mismatch"


def test_missing_vendor_po_grn_and_relationships(client, monkeypatch):
    invoice_missing_vendor = MATCHED_INVOICE.replace("ABC Pvt Ltd\n", "Invoice Header\n", 1)
    invoice = _upload_process(client, monkeypatch, "inv5.pdf", invoice_missing_vendor)
    po = _upload_process(client, monkeypatch, "po5.pdf", MATCHED_PO)
    grn = _upload_process(client, monkeypatch, "grn5.pdf", MATCHED_GRN)
    _confirm_relationships(client, invoice, po, grn)
    _clear_active_reviews(client, invoice["id"])
    missing_vendor = _run_three_way(client, invoice, po, grn).json()
    assert missing_vendor["status"] == "needs_review"
    assert missing_vendor["vendor_status"] == "needs_review"

    invoice2 = _upload_process(
        client,
        monkeypatch,
        "inv6.pdf",
        MATCHED_INVOICE.replace("PO Number: PO-1007\n", ""),
    )
    po2 = _upload_process(client, monkeypatch, "po6.pdf", MATCHED_PO)
    grn2 = _upload_process(client, monkeypatch, "grn6.pdf", MATCHED_GRN)
    _confirm_relationships(client, invoice2, po2, grn2)
    _clear_active_reviews(client, invoice2["id"])
    missing_po = _run_three_way(client, invoice2, po2, grn2).json()
    assert missing_po["po_reference_status"] == "needs_review"
    assert missing_po["status"] == "needs_review"

    invoice3 = _upload_process(
        client,
        monkeypatch,
        "inv7.pdf",
        MATCHED_INVOICE.replace("GRN Number: GRN-501\n", ""),
    )
    po3 = _upload_process(client, monkeypatch, "po7.pdf", MATCHED_PO)
    grn3 = _upload_process(client, monkeypatch, "grn7.pdf", MATCHED_GRN)
    _confirm_relationships(client, invoice3, po3, grn3)
    _clear_active_reviews(client, invoice3["id"])
    missing_grn = _run_three_way(client, invoice3, po3, grn3).json()
    assert missing_grn["grn_reference_status"] == "needs_review"
    assert missing_grn["status"] == "needs_review"
    assert missing_grn["status"] != "mismatch"

    invoice4 = _upload_process(client, monkeypatch, "inv8.pdf", MATCHED_INVOICE)
    po4 = _upload_process(client, monkeypatch, "po8.pdf", MATCHED_PO)
    grn4 = _upload_process(client, monkeypatch, "grn8.pdf", MATCHED_GRN)
    _clear_active_reviews(client, invoice4["id"])
    # No relationships confirmed
    missing_rel = _run_three_way(client, invoice4, po4, grn4).json()
    assert missing_rel["relationship_status"] == "needs_review"
    assert missing_rel["status"] == "needs_review"

    reviews = client.get(
        "/api/v1/reviews",
        params={"reason": ReviewReason.THREE_WAY_MATCH_NEEDS_REVIEW.value},
    ).json()
    assert reviews["total"] >= 1


def test_invalid_document_types_and_financial_reuse(client, monkeypatch):
    invoice = _upload_process(client, monkeypatch, "inv9.pdf", MATCHED_INVOICE)
    po = _upload_process(client, monkeypatch, "po9.pdf", MATCHED_PO)
    grn = _upload_process(client, monkeypatch, "grn9.pdf", MATCHED_GRN)
    bad = client.post(
        "/api/v1/validations/three-way",
        json={
            "invoice_document_id": po["id"],
            "purchase_order_document_id": invoice["id"],
            "goods_receipt_document_id": grn["id"],
        },
    )
    assert bad.status_code == 400

    financial_mismatch_invoice = MATCHED_INVOICE.replace("Total: 531,000", "Total: 999,000")
    inv_f = _upload_process(client, monkeypatch, "inv10.pdf", financial_mismatch_invoice)
    po_f = _upload_process(client, monkeypatch, "po10.pdf", MATCHED_PO)
    grn_f = _upload_process(client, monkeypatch, "grn10.pdf", MATCHED_GRN)
    _confirm_relationships(client, inv_f, po_f, grn_f)
    result = _run_three_way(client, inv_f, po_f, grn_f).json()
    assert result["financial_status"] == "mismatch"
    assert result["status"] == "mismatch"
    assert result["invoice_po_validation_id"] is not None

    # Existing Invoice↔PO validation API still works independently.
    pair = client.post(
        f"/api/v1/validations/invoice/{inv_f['invoice_id']}/purchase-order/{po_f['purchase_order_id']}"
    )
    assert pair.status_code == 200
    assert pair.json()["status"] == "mismatch"


def test_review_deduplication_for_three_way(client, monkeypatch):
    invoice = _upload_process(
        client,
        monkeypatch,
        "inv11.pdf",
        MATCHED_INVOICE.replace("ABC Pvt Ltd\n", "Other Co\n", 1),
    )
    po = _upload_process(client, monkeypatch, "po11.pdf", MATCHED_PO)
    grn = _upload_process(client, monkeypatch, "grn11.pdf", MATCHED_GRN)
    _confirm_relationships(client, invoice, po, grn)
    _clear_active_reviews(client, invoice["id"])
    _run_three_way(client, invoice, po, grn)
    _run_three_way(client, invoice, po, grn)
    reviews = client.get(
        "/api/v1/reviews",
        params={"reason": ReviewReason.THREE_WAY_MATCH_MISMATCH.value},
    ).json()
    matching = [item for item in reviews["items"] if item["document_id"] == invoice["id"]]
    assert len(matching) == 1
