from __future__ import annotations

from datetime import datetime, timezone
import re
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.models.invoice import Invoice
from app.models.purchase_order import PurchaseOrder
from app.models.vendor import Vendor
from app.schemas.vendor import (
    VendorCreate,
    VendorDetailResponse,
    VendorInvoiceSummary,
    VendorListResponse,
    VendorPurchaseOrderSummary,
    VendorResponse,
    VendorSummary,
    VendorUpdate,
)


def normalize_vendor_name(name: str | None) -> str | None:
    if name is None:
        return None
    text = str(name).strip().lower()
    if not text:
        return None
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


class VendorService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def find_or_create_vendor(self, vendor_name: str | None) -> Vendor | None:
        display_name = (vendor_name or "").strip()
        normalized = normalize_vendor_name(display_name)
        if not normalized:
            return None

        existing = self.db.scalar(
            select(Vendor).where(Vendor.normalized_name == normalized)
        )
        if existing is not None:
            return existing

        now = datetime.now(timezone.utc)
        vendor = Vendor(
            name=display_name,
            normalized_name=normalized,
            created_at=now,
            updated_at=now,
        )
        self.db.add(vendor)
        self.db.flush()
        return vendor

    def link_existing_records(self) -> dict[str, int]:
        invoices_linked = 0
        purchase_orders_linked = 0

        invoices = self.db.scalars(
            select(Invoice).where(
                Invoice.vendor_name.is_not(None),
                Invoice.vendor_id.is_(None),
            )
        ).all()
        for invoice in invoices:
            vendor = self.find_or_create_vendor(invoice.vendor_name)
            if vendor is None:
                continue
            invoice.vendor_id = vendor.id
            invoices_linked += 1

        purchase_orders = self.db.scalars(
            select(PurchaseOrder).where(
                PurchaseOrder.vendor_name.is_not(None),
                PurchaseOrder.vendor_id.is_(None),
            )
        ).all()
        for purchase_order in purchase_orders:
            vendor = self.find_or_create_vendor(purchase_order.vendor_name)
            if vendor is None:
                continue
            purchase_order.vendor_id = vendor.id
            purchase_orders_linked += 1

        self.db.commit()
        return {
            "invoices_linked": invoices_linked,
            "purchase_orders_linked": purchase_orders_linked,
        }

    def list_vendors(self, page: int = 1, page_size: int = 50) -> VendorListResponse:
        if page < 1:
            raise AppError("page must be >= 1.", status_code=400)
        if page_size < 1 or page_size > 100:
            raise AppError("page_size must be between 1 and 100.", status_code=400)

        total = self.db.scalar(select(func.count()).select_from(Vendor)) or 0
        invoice_counts = dict(
            self.db.execute(
                select(Invoice.vendor_id, func.count())
                .where(Invoice.vendor_id.is_not(None))
                .group_by(Invoice.vendor_id)
            ).all()
        )
        po_counts = dict(
            self.db.execute(
                select(PurchaseOrder.vendor_id, func.count())
                .where(PurchaseOrder.vendor_id.is_not(None))
                .group_by(PurchaseOrder.vendor_id)
            ).all()
        )

        vendors = self.db.scalars(
            select(Vendor)
            .order_by(Vendor.name.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()

        items = [
            VendorResponse(
                id=vendor.id,
                name=vendor.name,
                email=vendor.email,
                phone=vendor.phone,
                tax_id=vendor.tax_id,
                invoice_count=int(invoice_counts.get(vendor.id, 0)),
                purchase_order_count=int(po_counts.get(vendor.id, 0)),
                created_at=vendor.created_at,
            )
            for vendor in vendors
        ]
        return VendorListResponse(items=items, total=total, page=page, page_size=page_size)

    def get_vendor(self, vendor_id: uuid.UUID) -> VendorDetailResponse:
        vendor = self._get_or_404(vendor_id)

        invoices = self.db.scalars(
            select(Invoice)
            .where(Invoice.vendor_id == vendor.id)
            .order_by(Invoice.created_at.desc())
        ).all()
        purchase_orders = self.db.scalars(
            select(PurchaseOrder)
            .where(PurchaseOrder.vendor_id == vendor.id)
            .order_by(PurchaseOrder.created_at.desc())
        ).all()

        return VendorDetailResponse(
            id=vendor.id,
            name=vendor.name,
            normalized_name=vendor.normalized_name,
            email=vendor.email,
            phone=vendor.phone,
            address=vendor.address,
            tax_id=vendor.tax_id,
            created_at=vendor.created_at,
            updated_at=vendor.updated_at,
            summary=VendorSummary(
                invoice_count=len(invoices),
                purchase_order_count=len(purchase_orders),
            ),
            invoices=[
                VendorInvoiceSummary(
                    id=invoice.id,
                    invoice_number=invoice.invoice_number,
                    invoice_date=invoice.invoice_date,
                    total_amount=invoice.total_amount,
                    currency=invoice.currency,
                    document_id=invoice.document_id,
                )
                for invoice in invoices
            ],
            purchase_orders=[
                VendorPurchaseOrderSummary(
                    id=po.id,
                    po_number=po.po_number,
                    po_date=po.po_date,
                    total_amount=po.total_amount,
                    currency=po.currency,
                    document_id=po.document_id,
                )
                for po in purchase_orders
            ],
        )

    def create_vendor(self, payload: VendorCreate) -> VendorDetailResponse:
        display_name = payload.name.strip()
        normalized = normalize_vendor_name(display_name)
        if not normalized:
            raise AppError("Vendor name is required.", status_code=400)

        existing = self.db.scalar(
            select(Vendor).where(Vendor.normalized_name == normalized)
        )
        if existing is not None:
            raise AppError(
                "A vendor with this name already exists.",
                status_code=409,
            )

        now = datetime.now(timezone.utc)
        vendor = Vendor(
            name=display_name,
            normalized_name=normalized,
            email=self._clean_optional(payload.email),
            phone=self._clean_optional(payload.phone),
            address=self._clean_optional(payload.address),
            tax_id=self._clean_optional(payload.tax_id),
            created_at=now,
            updated_at=now,
        )
        self.db.add(vendor)
        self.db.commit()
        self.db.refresh(vendor)
        return self.get_vendor(vendor.id)

    def update_vendor(self, vendor_id: uuid.UUID, payload: VendorUpdate) -> VendorDetailResponse:
        vendor = self._get_or_404(vendor_id)
        data = payload.model_dump(exclude_unset=True)

        if "name" in data:
            display_name = (data["name"] or "").strip()
            normalized = normalize_vendor_name(display_name)
            if not normalized:
                raise AppError("Vendor name is required.", status_code=400)
            conflict = self.db.scalar(
                select(Vendor).where(
                    Vendor.normalized_name == normalized,
                    Vendor.id != vendor.id,
                )
            )
            if conflict is not None:
                raise AppError(
                    "A vendor with this name already exists.",
                    status_code=409,
                )
            vendor.name = display_name
            vendor.normalized_name = normalized

        for field in ("email", "phone", "address", "tax_id"):
            if field in data:
                setattr(vendor, field, self._clean_optional(data[field]))

        vendor.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(vendor)
        return self.get_vendor(vendor.id)

    def delete_vendor(self, vendor_id: uuid.UUID) -> None:
        vendor = self._get_or_404(vendor_id)
        invoice_count = self.db.scalar(
            select(func.count()).select_from(Invoice).where(Invoice.vendor_id == vendor.id)
        ) or 0
        po_count = self.db.scalar(
            select(func.count())
            .select_from(PurchaseOrder)
            .where(PurchaseOrder.vendor_id == vendor.id)
        ) or 0

        if invoice_count or po_count:
            raise AppError(
                "Cannot delete vendor while invoices or purchase orders are linked to it.",
                status_code=409,
            )

        self.db.delete(vendor)
        self.db.commit()

    def _get_or_404(self, vendor_id: uuid.UUID) -> Vendor:
        vendor = self.db.get(Vendor, vendor_id)
        if vendor is None:
            raise AppError("Vendor not found.", status_code=404)
        return vendor

    @staticmethod
    def _clean_optional(value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None
