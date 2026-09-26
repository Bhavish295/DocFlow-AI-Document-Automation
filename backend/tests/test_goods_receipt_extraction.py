from app.services.classification import RuleBasedDocumentClassifier
from app.services.goods_receipt_extraction import RuleBasedGoodsReceiptExtractor


GOODS_RECEIPT_TEXT = """
GOODS RECEIPT NOTE
GRN Number: GRN-501
Supplier: Demo Parts Co
PO Number: PO-1007
Received Date: 12 March 2026
Quantity Received: 20
"""

MISSING_GRN_NUMBER_TEXT = """
GOODS RECEIPT NOTE
Supplier: Demo Parts Co
PO Number: PO-1007
Received Date: 12 March 2026
Quantity Received: 20
"""


def test_classify_goods_receipt():
    result = RuleBasedDocumentClassifier().classify(GOODS_RECEIPT_TEXT)
    assert result.document_type == "goods_receipt"
    assert result.confidence >= 0.55


def test_extract_complete_goods_receipt():
    result = RuleBasedGoodsReceiptExtractor().extract(GOODS_RECEIPT_TEXT)
    assert result.grn_number == "GRN-501"
    assert result.po_number == "PO-1007"
    assert result.vendor_name is not None
    assert result.grn_date is not None
    assert result.total_received_quantity is not None
    assert float(result.total_received_quantity) == 20.0
    assert result.extraction_confidence >= 0.85


def test_missing_grn_number_stays_null():
    result = RuleBasedGoodsReceiptExtractor().extract(MISSING_GRN_NUMBER_TEXT)
    assert result.grn_number is None
    assert result.po_number == "PO-1007"
    assert result.extraction_confidence < 0.85


def test_grn_date_vendor_po_and_confidence():
    result = RuleBasedGoodsReceiptExtractor().extract(GOODS_RECEIPT_TEXT)
    assert result.grn_date.isoformat() == "2026-03-12"
    assert "Demo" in (result.vendor_name or "")
    assert result.po_number == "PO-1007"
    assert 0.0 <= result.extraction_confidence <= 1.0
