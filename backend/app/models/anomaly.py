"""ML anomaly detection persistence models (Step 14)."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import uuid

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid

from app.core.database import Base

JsonType = JSON().with_variant(JSONB(), "postgresql")


class AnomalyModelRunStatus(str, Enum):
    TRAINING = "training"
    READY = "ready"
    FAILED = "failed"
    INSUFFICIENT_DATA = "insufficient_data"


class AnomalyStatus(str, Enum):
    NORMAL = "normal"
    UNUSUAL = "unusual"
    ANOMALY = "anomaly"
    REQUIRES_REVIEW = "requires_review"


class AnomalyModelRun(Base):
    __tablename__ = "anomaly_model_runs"
    __table_args__ = (
        Index("ix_anomaly_model_runs_status", "status"),
        Index("ix_anomaly_model_runs_trained_at", "trained_at"),
        Index("ix_anomaly_model_runs_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    trained_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    feature_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    model_metadata: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    anomalies = relationship(
        "DocumentAnomaly",
        back_populates="model_run",
        cascade="all, delete-orphan",
    )


class DocumentAnomaly(Base):
    __tablename__ = "document_anomalies"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "model_run_id",
            name="uq_document_anomalies_document_model_run",
        ),
        Index("ix_document_anomalies_document_id", "document_id"),
        Index("ix_document_anomalies_model_run_id", "model_run_id"),
        Index("ix_document_anomalies_status", "status"),
        Index("ix_document_anomalies_anomaly_score", "anomaly_score"),
        Index("ix_document_anomalies_detected_at", "detected_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    model_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("anomaly_model_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    anomaly_score: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    reasons: Mapped[list | None] = mapped_column(JsonType, nullable=True)
    feature_values: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    model_run = relationship("AnomalyModelRun", back_populates="anomalies")
    document = relationship("Document")
