from datetime import date
from decimal import Decimal

from app.services.invoice_extraction import RuleBasedInvoiceExtractor, parse_amount


COMPLETE_INVOICE = """
ABC Pvt Ltd
Invoice No: INV-1827
Date: 10-09-2026
Subtotal: 450,000
Tax: 81,000
Total: 531,000
Currency: PKR
"""

PARTIAL_INVOICE = """
Invoice Number: INV-9
Some notes without money fields
"""


def test_complete_invoice_extraction():
    result = RuleBasedInvoiceExtractor().extract(COMPLETE_INVOICE)

    assert result.vendor_name == "ABC Pvt Ltd"
    assert result.invoice_number == "INV-1827"
    assert result.invoice_date == date(2026, 9, 10)
    assert result.subtotal == Decimal("450000.00")
    assert result.tax_amount == Decimal("81000.00")
    assert result.total_amount == Decimal("531000.00")
    assert result.currency == "PKR"
    assert result.extraction_confidence >= 0.85


def test_vendor_extraction():
    result = RuleBasedInvoiceExtractor().extract(COMPLETE_INVOICE)
    assert result.vendor_name == "ABC Pvt Ltd"


def test_invoice_number_extraction_variants():
    samples = [
        ("Invoice Number: AB-100", "AB-100"),
        ("Invoice No: INV-55", "INV-55"),
        ("Invoice #: 9001", "9001"),
        ("Inv No INV-77", "INV-77"),
        ("INV No: X-12", "X-12"),
    ]
    extractor = RuleBasedInvoiceExtractor()
    for text, expected in samples:
        assert extractor.extract(text).invoice_number == expected


def test_date_extraction():
    result = RuleBasedInvoiceExtractor().extract("Invoice Date: 10-09-2026\nTotal: 10")
    assert result.invoice_date == date(2026, 9, 10)


def test_subtotal_extraction():
    result = RuleBasedInvoiceExtractor().extract("Sub Total: 1,250.50\nTax: 10\nTotal: 1260.50")
    assert result.subtotal == Decimal("1250.50")


def test_tax_extraction_variants():
    for label in ("Tax", "VAT", "GST", "Sales Tax"):
        result = RuleBasedInvoiceExtractor().extract(f"{label}: 81,000\nTotal: 100")
        assert result.tax_amount == Decimal("81000.00")


def test_total_extraction_variants():
    samples = [
        "Grand Total: 531,000",
        "Total Amount: 531000",
        "Amount Due: 531,000.00",
        "Total: 531,000",
    ]
    extractor = RuleBasedInvoiceExtractor()
    for text in samples:
        assert extractor.extract(text).total_amount == Decimal("531000.00")


def test_currency_extraction_variants():
    extractor = RuleBasedInvoiceExtractor()
    assert extractor.extract("Total: PKR 531,000").currency == "PKR"
    assert extractor.extract("Total: Rs. 531,000").currency == "PKR"
    assert extractor.extract("Total: $120.00").currency == "USD"
    assert extractor.extract("Currency: EUR\nTotal: 20").currency == "EUR"


def test_pkr_rs_amount_formats():
    extractor = RuleBasedInvoiceExtractor()
    assert extractor.extract("Total: Rs 531,000").total_amount == Decimal("531000.00")
    assert extractor.extract("Total: PKR 531,000.00").total_amount == Decimal("531000.00")


def test_decimal_amount_formats():
    assert parse_amount("531,000.00") == Decimal("531000.00")
    assert parse_amount("531000") == Decimal("531000.00")
    result = RuleBasedInvoiceExtractor().extract("Net Amount: 99.99\nTotal: 99.99")
    assert result.subtotal == Decimal("99.99")


def test_missing_fields_return_null():
    result = RuleBasedInvoiceExtractor().extract(PARTIAL_INVOICE)
    assert result.invoice_number == "INV-9"
    assert result.subtotal is None
    assert result.tax_amount is None
    assert result.total_amount is None
    assert result.invoice_date is None
