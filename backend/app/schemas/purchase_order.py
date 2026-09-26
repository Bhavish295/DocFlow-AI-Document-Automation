import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_serializer


class PurchaseOrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    vendor_id: uuid.UUID | None = None
    po_number: str | None = None
    vendor_name: str | None = None
    po_date: date | None = None
    subtotal: Decimal | None = None
    tax_amount: Decimal | None = None
    total_amount: Decimal | None = None
    currency: str | None = None
    extraction_confidence: float | None = None
    created_at: datetime
    updated_at: datetime

    @field_serializer("subtotal", "tax_amount", "total_amount")
    def serialize_amounts(self, value: Decimal | None) -> float | None:
        if value is None:
            return None
        return float(value)
