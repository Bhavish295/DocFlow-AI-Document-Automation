"""Alembic revision: document ingestions for batch and email attachment intake."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260324_0020"
down_revision: str | None = "20260324_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_ingestions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("source_reference", sa.String(length=255), nullable=True),
        sa.Column("source_identity", sa.String(length=500), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("processing_job_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["processing_job_id"],
            ["document_processing_jobs.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_identity", name="uq_document_ingestions_source_identity"),
    )
    op.create_index(
        "ix_document_ingestions_source_type",
        "document_ingestions",
        ["source_type"],
        unique=False,
    )
    op.create_index(
        "ix_document_ingestions_source_identity",
        "document_ingestions",
        ["source_identity"],
        unique=False,
    )
    op.create_index(
        "ix_document_ingestions_document_id",
        "document_ingestions",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        "ix_document_ingestions_processing_job_id",
        "document_ingestions",
        ["processing_job_id"],
        unique=False,
    )
    op.create_index(
        "ix_document_ingestions_status",
        "document_ingestions",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_document_ingestions_created_at",
        "document_ingestions",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_document_ingestions_created_at", table_name="document_ingestions")
    op.drop_index("ix_document_ingestions_status", table_name="document_ingestions")
    op.drop_index("ix_document_ingestions_processing_job_id", table_name="document_ingestions")
    op.drop_index("ix_document_ingestions_document_id", table_name="document_ingestions")
    op.drop_index("ix_document_ingestions_source_identity", table_name="document_ingestions")
    op.drop_index("ix_document_ingestions_source_type", table_name="document_ingestions")
    op.drop_table("document_ingestions")
