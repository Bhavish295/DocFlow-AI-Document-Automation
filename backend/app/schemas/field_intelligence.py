import uuid

from pydantic import BaseModel, Field


class FieldIntelligenceField(BaseModel):
    field_name: str
    value: float | str | None = None
    status: str
    confidence: float = Field(ge=0, le=1)
    issues: list[str] = Field(default_factory=list)


class FieldIntelligenceResponse(BaseModel):
    document_id: uuid.UUID
    document_type: str | None = None
    overall_status: str
    overall_confidence: float = Field(ge=0, le=1)
    fields: list[FieldIntelligenceField]
    issues: list[str]
    review_required: bool
