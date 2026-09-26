from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import uuid

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.core.database import Base


class ReviewStatus(str, Enum):
    PENDING = "pending"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class ReviewPriority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ReviewReason(str, Enum):
    PROCESSING_FAILED = "processing_failed"
    UNKNOWN_DOCUMENT_TYPE = "unknown_document_type"
    LOW_CLASSIFICATION_CONFIDENCE = "low_classification_confidence"
    LOW_EXTRACTION_CONFIDENCE = "low_extraction_confidence"
    MISSING_REQUIRED_FIELDS = "missing_required_fields"
    VALIDATION_MISMATCH = "validation_mismatch"
    FIELD_MISSING = "field_missing"
    FIELD_INVALID = "field_invalid"
    FIELD_SUSPICIOUS = "field_suspicious"
    FINANCIAL_CONSISTENCY_MISMATCH = "financial_consistency_mismatch"
    CLASSIFICATION_MODEL_DISAGREEMENT = "classification_model_disagreement"
    THREE_WAY_MATCH_MISMATCH = "three_way_match_mismatch"
    THREE_WAY_MATCH_NEEDS_REVIEW = "three_way_match_needs_review"


ACTIVE_REVIEW_STATUSES = {
    ReviewStatus.PENDING.value,
    ReviewStatus.IN_REVIEW.value,
}


class DocumentReview(Base):
    __tablename__ = "document_reviews"
    __table_args__ = (
        Index("ix_document_reviews_document_id", "document_id"),
        Index("ix_document_reviews_status", "status"),
        Index("ix_document_reviews_priority", "priority"),
        Index("ix_document_reviews_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=ReviewStatus.PENDING.value,
    )
    priority: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ReviewPriority.MEDIUM.value,
    )
    reason: Mapped[str] = mapped_column(String(100), nullable=False)
    details: Mapped[str] = mapped_column(Text, nullable=False)
    reviewer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    document = relationship("Document", back_populates="reviews")
