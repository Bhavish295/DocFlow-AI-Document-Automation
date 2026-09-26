"""Alembic revision: document processing jobs."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260324_0018"
down_revision: str | None = "20260324_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_processing_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("job_type", sa.String(length=50), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("current_stage", sa.String(length=50), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("parent_job_id", sa.Uuid(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["parent_job_id"],
            ["document_processing_jobs.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_document_processing_jobs_document_id",
        "document_processing_jobs",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        "ix_document_processing_jobs_status",
        "document_processing_jobs",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_document_processing_jobs_created_at",
        "document_processing_jobs",
        ["created_at"],
        unique=False,
    )
    # At most one queued/running job per document (PostgreSQL).
    op.create_index(
        "uq_document_processing_jobs_active_document",
        "document_processing_jobs",
        ["document_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_document_processing_jobs_active_document",
        table_name="document_processing_jobs",
    )
    op.drop_index("ix_document_processing_jobs_created_at", table_name="document_processing_jobs")
    op.drop_index("ix_document_processing_jobs_status", table_name="document_processing_jobs")
    op.drop_index("ix_document_processing_jobs_document_id", table_name="document_processing_jobs")
    op.drop_table("document_processing_jobs")
