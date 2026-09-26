from __future__ import annotations

from datetime import date, datetime, timezone
import uuid

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.core.database import Base


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (
        UniqueConstraint("document_id", name="uq_purchase_orders_document_id"),
        Index("ix_purchase_orders_po_number", "po_number"),
        Index("ix_purchase_orders_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("vendors.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    po_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    vendor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    po_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    subtotal: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    tax_amount: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    total_amount: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    extraction_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
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

    document = relationship("Document", back_populates="purchase_order")
    vendor = relationship("Vendor", back_populates="purchase_orders")
    validations = relationship("DocumentValidation", back_populates="purchase_order")
