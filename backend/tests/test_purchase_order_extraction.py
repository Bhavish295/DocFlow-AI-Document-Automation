from datetime import date
from decimal import Decimal

from app.services.purchase_order_extraction import RuleBasedPurchaseOrderExtractor
from app.services.invoice_extraction import parse_amount


COMPLETE_PO = """
ABC Pvt Ltd
Purchase Order
PO Number: PO-7788
PO Date: 01-09-2026
Subtotal: 450,000
Tax: 81,000
Total: 531,000
Currency: PKR
"""

PARTIAL_PO = """
PO No: PO-9
Notes only
"""


def test_complete_po_extraction():
    result = RuleBasedPurchaseOrderExtractor().extract(COMPLETE_PO)
    assert result.vendor_name == "ABC Pvt Ltd"
    assert result.po_number == "PO-7788"
    assert result.po_date == date(2026, 9, 1)
    assert result.subtotal == Decimal("450000.00")
    assert result.tax_amount == Decimal("81000.00")
    assert result.total_amount == Decimal("531000.00")
    assert result.currency == "PKR"
    assert result.extraction_confidence >= 0.85


def test_po_number_variants():
    samples = [
        ("PO Number: PO-1", "PO-1"),
        ("PO No: AB-2", "AB-2"),
        ("PO #: 9001", "9001"),
        ("Purchase Order Number: X-12", "X-12"),
        ("P.O. Number: PO-44", "PO-44"),
    ]
    extractor = RuleBasedPurchaseOrderExtractor()
    for text, expected in samples:
        assert extractor.extract(text).po_number == expected


def test_po_date_extraction():
    result = RuleBasedPurchaseOrderExtractor().extract("Purchase Order Date: 01-09-2026\nTotal: 10")
    assert result.po_date == date(2026, 9, 1)


def test_po_vendor_extraction():
    assert RuleBasedPurchaseOrderExtractor().extract(COMPLETE_PO).vendor_name == "ABC Pvt Ltd"


def test_po_subtotal_tax_total_currency():
    extractor = RuleBasedPurchaseOrderExtractor()
    result = extractor.extract(COMPLETE_PO)
    assert result.subtotal == Decimal("450000.00")
    assert result.tax_amount == Decimal("81000.00")
    assert result.total_amount == Decimal("531000.00")
    assert result.currency == "PKR"


def test_po_pkr_rs_and_decimal_formats():
    extractor = RuleBasedPurchaseOrderExtractor()
    assert extractor.extract("Total: Rs. 531,000").total_amount == Decimal("531000.00")
    assert extractor.extract("Total: PKR 531,000.00").total_amount == Decimal("531000.00")
    assert parse_amount("531,000.00") == Decimal("531000.00")


def test_po_missing_fields_null():
    result = RuleBasedPurchaseOrderExtractor().extract(PARTIAL_PO)
    assert result.po_number == "PO-9"
    assert result.subtotal is None
    assert result.tax_amount is None
    assert result.total_amount is None
    assert result.po_date is None
