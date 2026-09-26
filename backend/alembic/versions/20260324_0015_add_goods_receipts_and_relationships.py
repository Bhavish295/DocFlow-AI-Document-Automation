"""Alembic revision: goods receipts and document relationships."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260324_0015"
down_revision: str | None = "20260324_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "goods_receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("vendor_id", sa.Uuid(), nullable=True),
        sa.Column("grn_number", sa.String(length=100), nullable=True),
        sa.Column("grn_date", sa.Date(), nullable=True),
        sa.Column("vendor_name", sa.String(length=255), nullable=True),
        sa.Column("po_number", sa.String(length=100), nullable=True),
        sa.Column("total_received_quantity", sa.Numeric(precision=18, scale=3), nullable=True),
        sa.Column("extraction_confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", name="uq_goods_receipts_document_id"),
    )
    op.create_index("ix_goods_receipts_vendor_id", "goods_receipts", ["vendor_id"], unique=False)

    op.create_table(
        "document_relationships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_document_id", sa.Uuid(), nullable=False),
        sa.Column("target_document_id", sa.Uuid(), nullable=False),
        sa.Column("relationship_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("match_key", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_document_id",
            "target_document_id",
            "relationship_type",
            name="uq_document_relationships_pair_type",
        ),
    )
    op.create_index(
        "ix_document_relationships_source_document_id",
        "document_relationships",
        ["source_document_id"],
        unique=False,
    )
    op.create_index(
        "ix_document_relationships_target_document_id",
        "document_relationships",
        ["target_document_id"],
        unique=False,
    )
    op.create_index(
        "ix_document_relationships_relationship_type",
        "document_relationships",
        ["relationship_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_document_relationships_relationship_type", table_name="document_relationships")
    op.drop_index("ix_document_relationships_target_document_id", table_name="document_relationships")
    op.drop_index("ix_document_relationships_source_document_id", table_name="document_relationships")
    op.drop_table("document_relationships")
    op.drop_index("ix_goods_receipts_vendor_id", table_name="goods_receipts")
    op.drop_table("goods_receipts")
