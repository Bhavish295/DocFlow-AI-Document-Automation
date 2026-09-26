from datetime import datetime, timezone
from enum import Enum
import uuid

from sqlalchemy import DateTime, Float, Integer, String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.core.database import Base


class DocumentStatus(str, Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
    MANUAL_REVIEW = "manual_review"


class DocumentType(str, Enum):
    INVOICE = "invoice"
    PURCHASE_ORDER = "purchase_order"
    GOODS_RECEIPT = "goods_receipt"
    CONTRACT = "contract"
    RECEIPT = "receipt"
    BANK_STATEMENT = "bank_statement"
    OTHER = "other"


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_content_hash", "content_hash"),
        Index("ix_documents_status_uploaded_at", "status", "uploaded_at"),
        Index("ix_documents_document_type_uploaded_at", "document_type", "uploaded_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    file_type: Mapped[str] = mapped_column(String(50), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=DocumentStatus.UPLOADED.value,
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    document_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    classification_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    rule_based_document_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    rule_based_classification_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    ml_document_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ml_classification_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    classification_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    rag_index_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    rag_index_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    rag_indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    invoice = relationship(
        "Invoice",
        back_populates="document",
        uselist=False,
        cascade="all, delete-orphan",
    )
    purchase_order = relationship(
        "PurchaseOrder",
        back_populates="document",
        uselist=False,
        cascade="all, delete-orphan",
    )
    goods_receipt = relationship(
        "GoodsReceipt",
        back_populates="document",
        uselist=False,
        cascade="all, delete-orphan",
    )
    line_items = relationship(
        "DocumentLineItem",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentLineItem.line_number",
    )
    relationships_as_source = relationship(
        "DocumentRelationship",
        foreign_keys="DocumentRelationship.source_document_id",
        back_populates="source_document",
        cascade="all, delete-orphan",
    )
    relationships_as_target = relationship(
        "DocumentRelationship",
        foreign_keys="DocumentRelationship.target_document_id",
        back_populates="target_document",
        cascade="all, delete-orphan",
    )
    reviews = relationship(
        "DocumentReview",
        back_populates="document",
        cascade="all, delete-orphan",
    )
    chunks = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
    )
    processing_jobs = relationship(
        "DocumentProcessingJob",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentProcessingJob.created_at.desc()",
    )
