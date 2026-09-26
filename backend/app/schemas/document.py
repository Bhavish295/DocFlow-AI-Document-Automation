import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    original_filename: str
    stored_filename: str
    file_type: str
    file_size: int
    status: str
    uploaded_at: datetime
    processing_error: str | None = None
    processed_at: datetime | None = None
    document_type: str | None = None
    classification_confidence: float | None = None
    rule_based_document_type: str | None = None
    rule_based_classification_confidence: float | None = None
    ml_document_type: str | None = None
    ml_classification_confidence: float | None = None
    classification_method: str | None = None
    has_invoice: bool = False
    has_purchase_order: bool = False
    has_goods_receipt: bool = False
    invoice_id: uuid.UUID | None = None
    purchase_order_id: uuid.UUID | None = None
    goods_receipt_id: uuid.UUID | None = None
    vendor_id: uuid.UUID | None = None
    vendor_name: str | None = None
    requires_review: bool = False
    rag_index_status: str | None = None
    rag_index_error: str | None = None
    rag_indexed_at: datetime | None = None
    content_hash: str | None = None
    duplicate_count: int = 0


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total_pages: int = 0
    has_next: bool = False
    has_previous: bool = False


class DocumentTextResponse(BaseModel):
    id: uuid.UUID
    original_filename: str
    status: str
    extracted_text: str | None = None
    processing_error: str | None = None
    processed_at: datetime | None = None


class ClassificationResponse(BaseModel):
    document_id: uuid.UUID
    document_type: str | None = None
    confidence: float | None = None
    status: str
    final_type: str | None = None
    final_confidence: float | None = None
    rule_based_type: str | None = None
    rule_based_confidence: float | None = None
    ml_type: str | None = None
    ml_confidence: float | None = None
    classification_method: str | None = None


class ClassificationPerClassMetrics(BaseModel):
    precision: float
    recall: float
    f1: float
    support: int


class ClassificationEvaluationResponse(BaseModel):
    """Holdout metrics on the local synthetic evaluation dataset only."""

    accuracy: float
    macro_precision: float
    macro_recall: float
    macro_f1: float
    per_class: dict[str, ClassificationPerClassMetrics]
    confusion_matrix: list[list[int]]
    labels: list[str]
    train_size: int
    test_size: int
    test_size_ratio: float
    note: str


class ClassificationTrainResponse(BaseModel):
    status: str
    example_count: int
    labels: list[str]
    model_available: bool
    model_version: str
    trained_at: str
    message: str
    evaluation: ClassificationEvaluationResponse | None = None


class ClassificationModelStatusResponse(BaseModel):
    model_available: bool
    model_version: str | None = None
    trained_at: str | None = None
    training_example_count: int | None = None
    supported_labels: list[str]
    algorithm: str
    evaluation_accuracy: float | None = None
    evaluation_macro_f1: float | None = None
    evaluation_timestamp: str | None = None


class MessageResponse(BaseModel):
    detail: str
