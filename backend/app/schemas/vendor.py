import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class VendorCreate(BaseModel):
    name: str
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    tax_id: str | None = None


class VendorUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    tax_id: str | None = None


class VendorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str | None = None
    phone: str | None = None
    tax_id: str | None = None
    invoice_count: int = 0
    purchase_order_count: int = 0
    created_at: datetime


class VendorListResponse(BaseModel):
    items: list[VendorResponse]
    total: int
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)


class VendorSummary(BaseModel):
    invoice_count: int
    purchase_order_count: int


class VendorInvoiceSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_number: str | None = None
    invoice_date: date | None = None
    total_amount: Decimal | None = None
    currency: str | None = None
    document_id: uuid.UUID

    @field_serializer("total_amount")
    def serialize_amount(self, value: Decimal | None) -> float | None:
        if value is None:
            return None
        return float(value)


class VendorPurchaseOrderSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    po_number: str | None = None
    po_date: date | None = None
    total_amount: Decimal | None = None
    currency: str | None = None
    document_id: uuid.UUID

    @field_serializer("total_amount")
    def serialize_amount(self, value: Decimal | None) -> float | None:
        if value is None:
            return None
        return float(value)


class VendorDetailResponse(BaseModel):
    id: uuid.UUID
    name: str
    normalized_name: str
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    tax_id: str | None = None
    created_at: datetime
    updated_at: datetime
    summary: VendorSummary
    invoices: list[VendorInvoiceSummary]
    purchase_orders: list[VendorPurchaseOrderSummary]
