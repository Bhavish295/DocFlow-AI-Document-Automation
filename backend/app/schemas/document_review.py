import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ReviewUpdate(BaseModel):
    status: str | None = None
    priority: str | None = None
    reviewer_notes: str | None = None


class ReviewActionRequest(BaseModel):
    reviewer_notes: str | None = None


class ReviewDocumentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    original_filename: str
    document_type: str | None = None
    status: str
    uploaded_at: datetime
    classification_confidence: float | None = None
    processing_error: str | None = None


class ReviewInvoiceSummary(BaseModel):
    id: uuid.UUID
    invoice_number: str | None = None
    invoice_date: str | None = None
    vendor_name: str | None = None
    subtotal: float | None = None
    tax_amount: float | None = None
    total_amount: float | None = None
    currency: str | None = None
    extraction_confidence: float | None = None


class ReviewPurchaseOrderSummary(BaseModel):
    id: uuid.UUID
    po_number: str | None = None
    po_date: str | None = None
    vendor_name: str | None = None
    subtotal: float | None = None
    tax_amount: float | None = None
    total_amount: float | None = None
    currency: str | None = None
    extraction_confidence: float | None = None


class ReviewValidationSummary(BaseModel):
    id: uuid.UUID
    status: str
    vendor_match: bool | None = None
    currency_match: bool | None = None
    subtotal_match: bool | None = None
    tax_match: bool | None = None
    total_match: bool | None = None
    mismatch_summary: str | None = None
    invoice_number: str | None = None
    po_number: str | None = None


class ReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    status: str
    priority: str
    reason: str
    details: str
    reviewer_notes: str | None = None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None
    document_filename: str | None = None
    document_type: str | None = None
    document_status: str | None = None


class ReviewListResponse(BaseModel):
    items: list[ReviewResponse]
    total: int
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total_pages: int = 0
    has_next: bool = False
    has_previous: bool = False


class ReviewDetailResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    status: str
    priority: str
    reason: str
    details: str
    reviewer_notes: str | None = None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None
    document: ReviewDocumentSummary
    invoice: ReviewInvoiceSummary | None = None
    purchase_order: ReviewPurchaseOrderSummary | None = None
    validation: ReviewValidationSummary | None = None
