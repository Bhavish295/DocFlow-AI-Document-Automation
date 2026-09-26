from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy import DateTime, Float, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.core.database import Base


class ThreeWayMatch(Base):
    """Persisted Invoice ↔ PO ↔ GRN matching result (assistive, not payment control)."""

    __tablename__ = "three_way_matches"
    __table_args__ = (
        UniqueConstraint(
            "invoice_document_id",
            "purchase_order_document_id",
            "goods_receipt_document_id",
            name="uq_three_way_matches_documents",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    purchase_order_document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    goods_receipt_document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    overall_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    vendor_status: Mapped[str] = mapped_column(String(50), nullable=False)
    po_reference_status: Mapped[str] = mapped_column(String(50), nullable=False)
    grn_reference_status: Mapped[str] = mapped_column(String(50), nullable=False)
    quantity_status: Mapped[str] = mapped_column(String(50), nullable=False)
    financial_status: Mapped[str] = mapped_column(String(50), nullable=False)
    relationship_status: Mapped[str] = mapped_column(String(50), nullable=False)
    matched_fields: Mapped[list | None] = mapped_column(JSON, nullable=True)
    mismatched_fields: Mapped[list | None] = mapped_column(JSON, nullable=True)
    missing_fields: Mapped[list | None] = mapped_column(JSON, nullable=True)
    dimension_details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    quantity_evidence: Mapped[list | None] = mapped_column(JSON, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    invoice_po_validation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("document_validations.id", ondelete="SET NULL"),
        nullable=True,
    )
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
