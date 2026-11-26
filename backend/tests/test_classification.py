from app.services.classification import RuleBasedDocumentClassifier


INVOICE_TEXT = """
INVOICE
Invoice Number: INV-1001
Bill To: Acme Corp
Subtotal: 200.00
Tax: 20.00
Total Amount: 220.00
Due Date: 2026-04-15
"""

PURCHASE_ORDER_TEXT = """
PURCHASE ORDER
PO Number: PO-7788
Order Number: ORD-55
Quantity: 12
Unit Price: 15.00
Ship To: Warehouse B
Order Date: 2026-03-01
"""

CONTRACT_TEXT = """
SERVICE AGREEMENT
This Contract is entered into by the Parties.
Terms and Conditions apply to all services.
Effective Date: January 1, 2026
Termination may occur with 30 days notice.
Governing Law: State of California
"""

RECEIPT_TEXT = """
STORE RECEIPT
Payment Received
Cash tendered: 50.00
Change: 7.50
Transaction #99821
Thank you for your purchase
Merchant: Corner Market
"""

BANK_STATEMENT_TEXT = """
Account Statement
Account Number: 123456789
Statement Period: Feb 1 - Feb 28
Opening Balance: 1,200.00
Transaction Date | Description | Debit | Credit | Balance
Closing Balance: 1,450.00
"""

GOODS_RECEIPT_TEXT = """
GOODS RECEIPT NOTE
GRN Number: GRN-501
Supplier: Demo Parts Co
PO Number: PO-1007
Received Date: 12 March 2026
Quantity Received: 20
"""

GOODS_RECEIPT_WITH_PO_TEXT = """
GOODS RECEIPT NOTE

GRN Number: GRN-1001
GRN Date: September 5, 2026

Vendor: ABC Pvt Ltd
PO Number: PO-7788
Currency: PKR

Item:
Description: Software Development Services
Item Code: DEV-001
Ordered Quantity: 1
Received Quantity: 1
Unit: Service
Unit Price: 450000
Line Total: 450000

Subtotal: 450000
Tax: 81000
Total: 531000

Received By: Store Department
Receipt Status: Received
"""

UNKNOWN_TEXT = """
Weekly team notes
Discussed roadmap priorities and staffing.
Follow up on office supplies next Monday.
"""


def test_classify_invoice():
    result = RuleBasedDocumentClassifier().classify(INVOICE_TEXT)
    assert result.document_type == "invoice"
    assert result.confidence >= 0.55


def test_classify_purchase_order():
    result = RuleBasedDocumentClassifier().classify(PURCHASE_ORDER_TEXT)
    assert result.document_type == "purchase_order"
    assert result.confidence >= 0.55


def test_classify_goods_receipt():
    result = RuleBasedDocumentClassifier().classify(GOODS_RECEIPT_TEXT)
    assert result.document_type == "goods_receipt"
    assert result.confidence >= 0.55


def test_classify_goods_receipt_with_po_number_stays_goods_receipt():
    result = RuleBasedDocumentClassifier().classify(GOODS_RECEIPT_WITH_PO_TEXT)
    assert result.document_type == "goods_receipt"
    assert result.confidence >= 0.55


def test_classify_contract():
    result = RuleBasedDocumentClassifier().classify(CONTRACT_TEXT)
    assert result.document_type == "contract"
    assert result.confidence >= 0.55


def test_classify_receipt():
    result = RuleBasedDocumentClassifier().classify(RECEIPT_TEXT)
    assert result.document_type == "receipt"
    assert result.confidence >= 0.55


def test_classify_bank_statement():
    result = RuleBasedDocumentClassifier().classify(BANK_STATEMENT_TEXT)
    assert result.document_type == "bank_statement"
    assert result.confidence >= 0.55


def test_classify_unknown_as_other():
    result = RuleBasedDocumentClassifier().classify(UNKNOWN_TEXT)
    assert result.document_type == "other"
    assert 0.0 <= result.confidence < 0.55


def test_classification_confidence_is_bounded():
    result = RuleBasedDocumentClassifier().classify(INVOICE_TEXT)
    assert 0.0 <= result.confidence <= 0.99
