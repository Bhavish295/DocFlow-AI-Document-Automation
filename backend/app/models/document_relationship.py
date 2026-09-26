from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import uuid

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.core.database import Base


class DocumentRelationshipType(str, Enum):
    INVOICE_PURCHASE_ORDER = "invoice_purchase_order"
    GOODS_RECEIPT_PURCHASE_ORDER = "goods_receipt_purchase_order"
    INVOICE_GOODS_RECEIPT = "invoice_goods_receipt"


class DocumentRelationshipStatus(str, Enum):
    CONFIRMED = "confirmed"


class DocumentRelationship(Base):
    """Explicit human-confirmed links between documents (foundation for 3-way matching)."""

    __tablename__ = "document_relationships"
    __table_args__ = (
        UniqueConstraint(
            "source_document_id",
            "target_document_id",
            "relationship_type",
            name="uq_document_relationships_pair_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    relationship_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=DocumentRelationshipStatus.CONFIRMED.value,
    )
    match_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
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

    source_document = relationship(
        "Document",
        foreign_keys=[source_document_id],
        back_populates="relationships_as_source",
    )
    target_document = relationship(
        "Document",
        foreign_keys=[target_document_id],
        back_populates="relationships_as_target",
    )
