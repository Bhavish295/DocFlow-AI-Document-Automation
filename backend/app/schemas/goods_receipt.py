import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_serializer


class GoodsReceiptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    vendor_id: uuid.UUID | None = None
    grn_number: str | None = None
    grn_date: date | None = None
    vendor_name: str | None = None
    po_number: str | None = None
    total_received_quantity: Decimal | None = None
    extraction_confidence: float | None = None
    created_at: datetime
    updated_at: datetime

    @field_serializer("total_received_quantity")
    def serialize_quantity(self, value: Decimal | None) -> float | None:
        if value is None:
            return None
        return float(value)
