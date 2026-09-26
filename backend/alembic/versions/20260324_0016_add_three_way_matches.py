"""Alembic revision: three-way match persistence table."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260324_0016"
down_revision: str | None = "20260324_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "three_way_matches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("invoice_document_id", sa.Uuid(), nullable=False),
        sa.Column("purchase_order_document_id", sa.Uuid(), nullable=False),
        sa.Column("goods_receipt_document_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("overall_confidence", sa.Float(), nullable=True),
        sa.Column("vendor_status", sa.String(length=50), nullable=False),
        sa.Column("po_reference_status", sa.String(length=50), nullable=False),
        sa.Column("grn_reference_status", sa.String(length=50), nullable=False),
        sa.Column("quantity_status", sa.String(length=50), nullable=False),
        sa.Column("financial_status", sa.String(length=50), nullable=False),
        sa.Column("relationship_status", sa.String(length=50), nullable=False),
        sa.Column("matched_fields", sa.JSON(), nullable=True),
        sa.Column("mismatched_fields", sa.JSON(), nullable=True),
        sa.Column("missing_fields", sa.JSON(), nullable=True),
        sa.Column("dimension_details", sa.JSON(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("invoice_po_validation_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["invoice_document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["purchase_order_document_id"], ["documents.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["goods_receipt_document_id"], ["documents.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["invoice_po_validation_id"], ["document_validations.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "invoice_document_id",
            "purchase_order_document_id",
            "goods_receipt_document_id",
            name="uq_three_way_matches_documents",
        ),
    )
    op.create_index(
        "ix_three_way_matches_invoice_document_id",
        "three_way_matches",
        ["invoice_document_id"],
        unique=False,
    )
    op.create_index(
        "ix_three_way_matches_purchase_order_document_id",
        "three_way_matches",
        ["purchase_order_document_id"],
        unique=False,
    )
    op.create_index(
        "ix_three_way_matches_goods_receipt_document_id",
        "three_way_matches",
        ["goods_receipt_document_id"],
        unique=False,
    )
    op.create_index(
        "ix_three_way_matches_status",
        "three_way_matches",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_three_way_matches_status", table_name="three_way_matches")
    op.drop_index(
        "ix_three_way_matches_goods_receipt_document_id", table_name="three_way_matches"
    )
    op.drop_index(
        "ix_three_way_matches_purchase_order_document_id", table_name="three_way_matches"
    )
    op.drop_index("ix_three_way_matches_invoice_document_id", table_name="three_way_matches")
    op.drop_table("three_way_matches")
