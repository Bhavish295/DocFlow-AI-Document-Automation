from datetime import datetime, timezone
import uuid

from sqlalchemy import func, select

from app.models.invoice import Invoice
from app.models.purchase_order import PurchaseOrder
from app.models.vendor import Vendor
from app.services.vendor_service import VendorService, normalize_vendor_name


def test_normalize_vendor_name_variants():
    assert normalize_vendor_name("ABC Traders") == "abc traders"
    assert normalize_vendor_name("ABC TRADERS") == "abc traders"
    assert normalize_vendor_name(" ABC Traders ") == "abc traders"
    assert normalize_vendor_name("ABC Traders.") == "abc traders"
    assert normalize_vendor_name("ABC  Traders") == "abc traders"
    assert normalize_vendor_name("ABC Traders Pvt. Ltd.") == "abc traders pvt ltd"
    assert normalize_vendor_name("ABC Traders Pvt Ltd") == "abc traders pvt ltd"
    assert normalize_vendor_name("   ") is None
    assert normalize_vendor_name(None) is None
    assert normalize_vendor_name("") is None


def test_find_or_create_and_missing_name(client):
    db = client.testing_session_local()
    try:
        service = VendorService(db)
        assert service.find_or_create_vendor(None) is None
        assert service.find_or_create_vendor("   ") is None

        first = service.find_or_create_vendor("ABC Traders")
        db.commit()
        second = service.find_or_create_vendor(" ABC TRADERS ")
        db.commit()
        other = service.find_or_create_vendor("XYZ Supplies")
        db.commit()

        assert first is not None
        assert second is not None
        assert first.id == second.id
        assert other is not None
        assert other.id != first.id
        assert (db.scalar(select(func.count()).select_from(Vendor)) or 0) == 2
    finally:
        db.close()


def test_link_existing_invoice_and_po_records(client):
    db = client.testing_session_local()
    try:
        now = datetime.now(timezone.utc)
        invoice = Invoice(
            document_id=uuid.uuid4(),
            vendor_name="ABC Traders",
            invoice_number="INV-1",
            created_at=now,
            updated_at=now,
        )
        purchase_order = PurchaseOrder(
            document_id=uuid.uuid4(),
            vendor_name="ABC TRADERS",
            po_number="PO-1",
            created_at=now,
            updated_at=now,
        )
        orphan = Invoice(
            document_id=uuid.uuid4(),
            vendor_name=None,
            invoice_number="INV-2",
            created_at=now,
            updated_at=now,
        )
        db.add_all([invoice, purchase_order, orphan])
        db.commit()

        result = VendorService(db).link_existing_records()
        db.refresh(invoice)
        db.refresh(purchase_order)
        db.refresh(orphan)

        assert result["invoices_linked"] == 1
        assert result["purchase_orders_linked"] == 1
        assert invoice.vendor_id is not None
        assert purchase_order.vendor_id == invoice.vendor_id
        assert orphan.vendor_id is None
        assert (db.scalar(select(func.count()).select_from(Vendor)) or 0) == 1
        assert invoice.vendor_name == "ABC Traders"
        assert purchase_order.vendor_name == "ABC TRADERS"
    finally:
        db.close()
