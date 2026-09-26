from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.core.database import Base


class ProcessingJobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ProcessingJobType(str, Enum):
    DOCUMENT_PROCESSING = "document_processing"


class ProcessingJobStage(str, Enum):
    QUEUED = "queued"
    TEXT_EXTRACTION = "text_extraction"
    CLASSIFICATION = "classification"
    STRUCTURED_EXTRACTION = "structured_extraction"
    LINE_ITEMS = "line_items"
    COMPLETED = "completed"


ACTIVE_JOB_STATUSES = (
    ProcessingJobStatus.QUEUED.value,
    ProcessingJobStatus.RUNNING.value,
)

STAGE_PROGRESS = {
    ProcessingJobStage.QUEUED.value: 0,
    ProcessingJobStage.TEXT_EXTRACTION.value: 20,
    ProcessingJobStage.CLASSIFICATION.value: 40,
    ProcessingJobStage.STRUCTURED_EXTRACTION.value: 60,
    ProcessingJobStage.LINE_ITEMS.value: 80,
    ProcessingJobStage.COMPLETED.value: 100,
}


class DocumentProcessingJob(Base):
    """Persistent background document-processing job record."""

    __tablename__ = "document_processing_jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=ProcessingJobStatus.QUEUED.value,
        index=True,
    )
    job_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=ProcessingJobType.DOCUMENT_PROCESSING.value,
    )
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_stage: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=ProcessingJobStage.QUEUED.value,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    parent_job_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("document_processing_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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

    document = relationship("Document", back_populates="processing_jobs")
    parent_job = relationship("DocumentProcessingJob", remote_side=[id])
