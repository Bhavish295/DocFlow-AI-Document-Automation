import io

from app.models.document_relationship import DocumentRelationshipType
from tests.test_goods_receipt_extraction import GOODS_RECEIPT_TEXT
from tests.test_invoice_extraction import COMPLETE_INVOICE
from tests.test_purchase_order_extraction import COMPLETE_PO


def _upload_and_process(client, monkeypatch, filename: str, text: str):
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


def test_processing_triggers_grn_extraction(client, monkeypatch):
    doc = _upload_and_process(client, monkeypatch, "grn.pdf", GOODS_RECEIPT_TEXT)
    assert doc["document_type"] == "goods_receipt"
    assert doc["has_goods_receipt"] is True
    assert doc["goods_receipt_id"] is not None

    grn = client.get(f"/api/v1/documents/{doc['id']}/goods-receipt")
    assert grn.status_code == 200
    body = grn.json()
    assert body["grn_number"] == "GRN-501"
    assert body["po_number"] == "PO-1007"


INVOICE_WITH_PO = COMPLETE_INVOICE + "\nPO Number: PO-1007\n"
INVOICE_WITH_GRN = COMPLETE_INVOICE + "\nGRN Number: GRN-501\n"
PO_TEXT = COMPLETE_PO.replace("PO-7788", "PO-1007")
GRN_TEXT = GOODS_RECEIPT_TEXT


def test_valid_relationships_and_rejections(client, monkeypatch):
    invoice = _upload_and_process(client, monkeypatch, "inv.pdf", INVOICE_WITH_PO)
    po = _upload_and_process(client, monkeypatch, "po.pdf", PO_TEXT)
    grn = _upload_and_process(client, monkeypatch, "grn.pdf", GRN_TEXT)

    created = client.post(
        "/api/v1/document-relationships",
        json={
            "source_document_id": invoice["id"],
            "target_document_id": po["id"],
            "relationship_type": DocumentRelationshipType.INVOICE_PURCHASE_ORDER.value,
            "match_key": "PO-1007",
        },
    )
    assert created.status_code == 201
    rel = created.json()
    assert rel["relationship_type"] == "invoice_purchase_order"
    assert rel["status"] == "confirmed"

    grn_po = client.post(
        "/api/v1/document-relationships",
        json={
            "source_document_id": grn["id"],
            "target_document_id": po["id"],
            "relationship_type": "goods_receipt_purchase_order",
            "match_key": "PO-1007",
        },
    )
    assert grn_po.status_code == 201

    inv_grn = client.post(
        "/api/v1/document-relationships",
        json={
            "source_document_id": invoice["id"],
            "target_document_id": grn["id"],
            "relationship_type": "invoice_goods_receipt",
            "match_key": "GRN-501",
        },
    )
    # Invoice text in this case has PO not GRN — still valid type combo
    assert inv_grn.status_code == 201

    invalid = client.post(
        "/api/v1/document-relationships",
        json={
            "source_document_id": po["id"],
            "target_document_id": invoice["id"],
            "relationship_type": "invoice_purchase_order",
        },
    )
    assert invalid.status_code == 400

    self_link = client.post(
        "/api/v1/document-relationships",
        json={
            "source_document_id": invoice["id"],
            "target_document_id": invoice["id"],
            "relationship_type": "invoice_purchase_order",
        },
    )
    assert self_link.status_code == 400

    duplicate = client.post(
        "/api/v1/document-relationships",
        json={
            "source_document_id": invoice["id"],
            "target_document_id": po["id"],
            "relationship_type": "invoice_purchase_order",
        },
    )
    assert duplicate.status_code == 409

    listed = client.get(f"/api/v1/document-relationships/{invoice['id']}")
    assert listed.status_code == 200
    assert listed.json()["total"] >= 2

    deleted = client.delete(f"/api/v1/document-relationships/{rel['id']}")
    assert deleted.status_code == 200
    after = client.get(f"/api/v1/document-relationships/{invoice['id']}")
    assert all(item["id"] != rel["id"] for item in after.json()["items"])


def test_relationship_suggestions_by_po_and_grn(client, monkeypatch):
    invoice = _upload_and_process(client, monkeypatch, "inv2.pdf", INVOICE_WITH_PO)
    po = _upload_and_process(client, monkeypatch, "po2.pdf", PO_TEXT)
    invoice_grn = _upload_and_process(client, monkeypatch, "inv3.pdf", INVOICE_WITH_GRN)
    grn = _upload_and_process(client, monkeypatch, "grn2.pdf", GRN_TEXT)

    po_suggestions = client.get(f"/api/v1/document-relationships/suggestions/{invoice['id']}")
    assert po_suggestions.status_code == 200
    po_items = po_suggestions.json()["items"]
    assert any(
        item["relationship_type"] == "invoice_purchase_order"
        and item["target_document_id"] == po["id"]
        and item["match_key"].replace(" ", "").upper().startswith("PO-1007")
        for item in po_items
    )

    grn_suggestions = client.get(f"/api/v1/document-relationships/suggestions/{invoice_grn['id']}")
    assert grn_suggestions.status_code == 200
    assert any(
        item["relationship_type"] == "invoice_goods_receipt"
        and item["target_document_id"] == grn["id"]
        for item in grn_suggestions.json()["items"]
    )

    # Confirming a suggestion does not create a review solely for the relationship.
    confirm = client.post(
        "/api/v1/document-relationships",
        json={
            "source_document_id": invoice["id"],
            "target_document_id": po["id"],
            "relationship_type": "invoice_purchase_order",
            "match_key": "PO-1007",
        },
    )
    assert confirm.status_code == 201
