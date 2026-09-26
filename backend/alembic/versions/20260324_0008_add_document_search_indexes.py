"""Alembic revision: add document search filter indexes."""

from collections.abc import Sequence

from alembic import op


revision: str = "20260324_0008"
down_revision: str | None = "20260324_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_documents_uploaded_at", "documents", ["uploaded_at"], unique=False)
    op.create_index("ix_documents_document_type", "documents", ["document_type"], unique=False)
    op.create_index("ix_documents_status", "documents", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_documents_status", table_name="documents")
    op.drop_index("ix_documents_document_type", table_name="documents")
    op.drop_index("ix_documents_uploaded_at", table_name="documents")
