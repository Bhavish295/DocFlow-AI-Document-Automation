"""Alembic revision: create document_reviews table."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260324_0009"
down_revision: str | None = "20260324_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.String(length=100), nullable=False),
        sa.Column("details", sa.Text(), nullable=False),
        sa.Column("reviewer_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_reviews_document_id", "document_reviews", ["document_id"], unique=False)
    op.create_index("ix_document_reviews_status", "document_reviews", ["status"], unique=False)
    op.create_index("ix_document_reviews_priority", "document_reviews", ["priority"], unique=False)
    op.create_index("ix_document_reviews_created_at", "document_reviews", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_document_reviews_created_at", table_name="document_reviews")
    op.drop_index("ix_document_reviews_priority", table_name="document_reviews")
    op.drop_index("ix_document_reviews_status", table_name="document_reviews")
    op.drop_index("ix_document_reviews_document_id", table_name="document_reviews")
    op.drop_table("document_reviews")
