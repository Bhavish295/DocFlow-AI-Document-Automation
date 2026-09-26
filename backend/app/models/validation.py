from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.core.database import Base


class ValidationStatus(str, Enum):
    MATCHED = "matched"
    MISMATCH = "mismatch"
    NEEDS_REVIEW = "needs_review"


class DocumentValidation(Base):
    __tablename__ = "document_validations"
    __table_args__ = (
        UniqueConstraint(
            "invoice_id",
            "purchase_order_id",
            name="uq_document_validations_invoice_po",
        ),
        Index("ix_document_validations_status", "status"),
        Index("ix_document_validations_created_at", "created_at"),
        Index("ix_document_validations_invoice_id", "invoice_id"),
        Index("ix_document_validations_purchase_order_id", "purchase_order_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
    )
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("purchase_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    vendor_match: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    currency_match: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    subtotal_match: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    tax_match: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    total_match: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    invoice_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    po_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    mismatch_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
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

    invoice = relationship("Invoice", back_populates="validations")
    purchase_order = relationship("PurchaseOrder", back_populates="validations")
