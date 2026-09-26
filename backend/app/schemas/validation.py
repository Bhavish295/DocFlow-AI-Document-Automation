import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ValidationResponse(BaseModel):
    id: uuid.UUID
    invoice_id: uuid.UUID
    purchase_order_id: uuid.UUID
    status: str
    vendor_match: bool | None = None
    currency_match: bool | None = None
    subtotal_match: bool | None = None
    tax_match: bool | None = None
    total_match: bool | None = None
    invoice_number: str | None = None
    po_number: str | None = None
    vendor_name: str | None = None
    mismatch_summary: str | None = None
    created_at: datetime
    updated_at: datetime


class ValidationListResponse(BaseModel):
    items: list[ValidationResponse]
    total: int
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
