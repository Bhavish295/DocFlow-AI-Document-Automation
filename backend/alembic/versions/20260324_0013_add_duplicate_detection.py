"""Alembic revision: content_hash + document_duplicates."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260324_0013"
down_revision: str | None = "20260324_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("content_hash", sa.String(length=64), nullable=True))
    op.create_index("ix_documents_content_hash", "documents", ["content_hash"], unique=False)

    op.create_table(
        "document_duplicates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_document_id", sa.Uuid(), nullable=False),
        sa.Column("duplicate_document_id", sa.Uuid(), nullable=False),
        sa.Column("detection_type", sa.String(length=50), nullable=False),
        sa.Column("similarity_score", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("reasons", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["source_document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["duplicate_document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_document_id",
            "duplicate_document_id",
            "detection_type",
            name="uq_document_duplicates_pair_type",
        ),
    )
    op.create_index(
        "ix_document_duplicates_source_document_id",
        "document_duplicates",
        ["source_document_id"],
        unique=False,
    )
    op.create_index(
        "ix_document_duplicates_duplicate_document_id",
        "document_duplicates",
        ["duplicate_document_id"],
        unique=False,
    )
    op.create_index(
        "ix_document_duplicates_detection_type",
        "document_duplicates",
        ["detection_type"],
        unique=False,
    )
    op.create_index(
        "ix_document_duplicates_status",
        "document_duplicates",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_document_duplicates_detected_at",
        "document_duplicates",
        ["detected_at"],
        unique=False,
    )
    op.create_index(
        "ix_document_duplicates_similarity_score",
        "document_duplicates",
        ["similarity_score"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_document_duplicates_similarity_score", table_name="document_duplicates")
    op.drop_index("ix_document_duplicates_detected_at", table_name="document_duplicates")
    op.drop_index("ix_document_duplicates_status", table_name="document_duplicates")
    op.drop_index("ix_document_duplicates_detection_type", table_name="document_duplicates")
    op.drop_index(
        "ix_document_duplicates_duplicate_document_id",
        table_name="document_duplicates",
    )
    op.drop_index("ix_document_duplicates_source_document_id", table_name="document_duplicates")
    op.drop_table("document_duplicates")
    op.drop_index("ix_documents_content_hash", table_name="documents")
    op.drop_column("documents", "content_hash")
