import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class DocumentLineItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    line_number: int
    description: str | None = None
    item_code: str | None = None
    quantity: Decimal | None = None
    quantity_type: str | None = None
    unit: str | None = None
    unit_price: Decimal | None = None
    line_total: Decimal | None = None
    currency: str | None = None
    created_at: datetime
    updated_at: datetime

    @field_serializer("quantity", "unit_price", "line_total")
    def serialize_numbers(self, value: Decimal | None) -> float | None:
        if value is None:
            return None
        return float(value)


class DocumentLineItemListResponse(BaseModel):
    document_id: uuid.UUID
    document_type: str | None = None
    items: list[DocumentLineItemResponse] = Field(default_factory=list)
    total: int = 0
