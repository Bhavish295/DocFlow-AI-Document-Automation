"""Duplicate detection persistence models (Step 15)."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import uuid

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid

from app.core.database import Base

JsonType = JSON().with_variant(JSONB(), "postgresql")


class DuplicateDetectionType(str, Enum):
    EXACT_DUPLICATE = "exact_duplicate"
    BUSINESS_DUPLICATE = "business_duplicate"
    SIMILAR_DUPLICATE = "similar_duplicate"


class DuplicateStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"


class DocumentDuplicate(Base):
    __tablename__ = "document_duplicates"
    __table_args__ = (
        UniqueConstraint(
            "source_document_id",
            "duplicate_document_id",
            "detection_type",
            name="uq_document_duplicates_pair_type",
        ),
        Index("ix_document_duplicates_source_document_id", "source_document_id"),
        Index("ix_document_duplicates_duplicate_document_id", "duplicate_document_id"),
        Index("ix_document_duplicates_detection_type", "detection_type"),
        Index("ix_document_duplicates_status", "status"),
        Index("ix_document_duplicates_detected_at", "detected_at"),
        Index("ix_document_duplicates_similarity_score", "similarity_score"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    duplicate_document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    detection_type: Mapped[str] = mapped_column(String(50), nullable=False)
    similarity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    reasons: Mapped[list | None] = mapped_column(JsonType, nullable=True)
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=DuplicateStatus.PENDING.value,
    )
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    source_document = relationship(
        "Document",
        foreign_keys=[source_document_id],
    )
    duplicate_document = relationship(
        "Document",
        foreign_keys=[duplicate_document_id],
    )
