"""Alembic revision: create purchase_orders table."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260324_0005"
down_revision: str | None = "20260324_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "purchase_orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("po_number", sa.String(length=100), nullable=True),
        sa.Column("vendor_name", sa.String(length=255), nullable=True),
        sa.Column("po_date", sa.Date(), nullable=True),
        sa.Column("subtotal", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("tax_amount", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("total_amount", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=True),
        sa.Column("extraction_confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", name="uq_purchase_orders_document_id"),
    )


def downgrade() -> None:
    op.drop_table("purchase_orders")
