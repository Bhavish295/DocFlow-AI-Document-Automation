"""Alembic revision: create document_validations table."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260324_0006"
down_revision: str | None = "20260324_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_validations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("invoice_id", sa.Uuid(), nullable=False),
        sa.Column("purchase_order_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("vendor_match", sa.Boolean(), nullable=True),
        sa.Column("currency_match", sa.Boolean(), nullable=True),
        sa.Column("subtotal_match", sa.Boolean(), nullable=True),
        sa.Column("tax_match", sa.Boolean(), nullable=True),
        sa.Column("total_match", sa.Boolean(), nullable=True),
        sa.Column("invoice_number", sa.String(length=100), nullable=True),
        sa.Column("po_number", sa.String(length=100), nullable=True),
        sa.Column("mismatch_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["purchase_order_id"], ["purchase_orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "invoice_id",
            "purchase_order_id",
            name="uq_document_validations_invoice_po",
        ),
    )


def downgrade() -> None:
    op.drop_table("document_validations")
