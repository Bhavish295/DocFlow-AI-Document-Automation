import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ThreeWayMatchRequest(BaseModel):
    invoice_document_id: uuid.UUID
    purchase_order_document_id: uuid.UUID
    goods_receipt_document_id: uuid.UUID


class ThreeWayDocumentSummary(BaseModel):
    document_id: uuid.UUID
    document_type: str | None = None
    filename: str | None = None
    record_id: uuid.UUID | None = None
    number: str | None = None
    vendor_name: str | None = None


class ThreeWayDimensionResult(BaseModel):
    name: str
    status: str
    detail: str | None = None


class ThreeWayQuantityEvidenceItem(BaseModel):
    item_key: str
    description: str | None = None
    item_code: str | None = None
    match_method: str | None = None
    po_quantity: float | None = None
    grn_quantity: float | None = None
    invoice_quantity: float | None = None
    status: str
    detail: str | None = None


class ThreeWayMatchResponse(BaseModel):
    id: uuid.UUID
    status: str
    overall_confidence: float | None = None
    invoice_document_id: uuid.UUID
    purchase_order_document_id: uuid.UUID
    goods_receipt_document_id: uuid.UUID
    invoice: ThreeWayDocumentSummary
    purchase_order: ThreeWayDocumentSummary
    goods_receipt: ThreeWayDocumentSummary
    vendor_status: str
    po_reference_status: str
    grn_reference_status: str
    quantity_status: str
    financial_status: str
    relationship_status: str
    dimensions: list[ThreeWayDimensionResult] = Field(default_factory=list)
    matched_fields: list[str] = Field(default_factory=list)
    mismatched_fields: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    quantity_evidence: list[ThreeWayQuantityEvidenceItem] = Field(default_factory=list)
    explanation: str
    invoice_po_validation_id: uuid.UUID | None = None
    invoice_po_validation_status: str | None = None
    created_at: datetime
    updated_at: datetime


class ThreeWayMatchListResponse(BaseModel):
    items: list[ThreeWayMatchResponse]
    total: int
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
