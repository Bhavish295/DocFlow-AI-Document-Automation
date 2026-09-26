from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import uuid

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, Uuid

from app.core.database import Base


class IngestionSourceType(str, Enum):
    MANUAL_UPLOAD = "manual_upload"
    BATCH_UPLOAD = "batch_upload"
    EMAIL_ATTACHMENT = "email_attachment"


class IngestionStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class DocumentIngestion(Base):
    """Provider-independent record of how a document entered the system."""

    __tablename__ = "document_ingestions"
    __table_args__ = (
        UniqueConstraint("source_identity", name="uq_document_ingestions_source_identity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_identity: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    processing_job_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("document_processing_jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=IngestionStatus.QUEUED.value,
        index=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Non-secret source metadata only (sender, subject, message_id, etc.)
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
