"""Alembic revision: document line items and three-way quantity evidence."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260324_0017"
down_revision: str | None = "20260324_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_line_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("item_code", sa.String(length=100), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=18, scale=3), nullable=True),
        sa.Column("quantity_type", sa.String(length=50), nullable=True),
        sa.Column("unit", sa.String(length=50), nullable=True),
        sa.Column("unit_price", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("line_total", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "line_number", name="uq_document_line_items_document_line"),
    )
    op.create_index(
        "ix_document_line_items_document_id",
        "document_line_items",
        ["document_id"],
        unique=False,
    )
    op.add_column("three_way_matches", sa.Column("quantity_evidence", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("three_way_matches", "quantity_evidence")
    op.drop_index("ix_document_line_items_document_id", table_name="document_line_items")
    op.drop_table("document_line_items")
