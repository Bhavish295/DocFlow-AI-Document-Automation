from __future__ import annotations

from datetime import date, datetime, timezone
import uuid

from sqlalchemy import Date, DateTime, Float, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.core.database import Base


class GoodsReceipt(Base):
    """Extracted Goods Receipt / GRN fields used for matching (not payment amounts)."""

    __tablename__ = "goods_receipts"
    __table_args__ = (UniqueConstraint("document_id", name="uq_goods_receipts_document_id"),)

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
    grn_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    grn_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    vendor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    po_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    total_received_quantity: Mapped[float | None] = mapped_column(Numeric(18, 3), nullable=True)
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

    document = relationship("Document", back_populates="goods_receipt")
    vendor = relationship("Vendor", back_populates="goods_receipts")
