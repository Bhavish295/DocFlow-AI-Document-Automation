"""Alembic revision: create document_chunks and RAG document fields."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision: str = "20260324_0010"
down_revision: str | None = "20260324_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("rag_index_status", sa.String(length=50), nullable=True))
    op.add_column("documents", sa.Column("rag_index_error", sa.Text(), nullable=True))
    op.add_column("documents", sa.Column("rag_indexed_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("embedding", sa.Text(), nullable=True),
        sa.Column("character_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_document_chunks_document_index"),
        sa.UniqueConstraint("document_id", "content_hash", name="uq_document_chunks_document_hash"),
    )
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"], unique=False)
    op.create_index("ix_document_chunks_content_hash", "document_chunks", ["content_hash"], unique=False)
    op.create_index("ix_document_chunks_created_at", "document_chunks", ["created_at"], unique=False)

    # Prefer pgvector when the extension is installed on the PostgreSQL host.
    # If unavailable, embeddings remain JSON text and retrieval uses Python cosine similarity.
    conn = op.get_bind()
    conn.execute(text("SAVEPOINT before_pgvector"))
    try:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.execute(
            text(
                "ALTER TABLE document_chunks "
                "ALTER COLUMN embedding TYPE vector(384) USING NULL"
            )
        )
        conn.execute(text("RELEASE SAVEPOINT before_pgvector"))
    except Exception:
        conn.execute(text("ROLLBACK TO SAVEPOINT before_pgvector"))


def downgrade() -> None:
    op.drop_index("ix_document_chunks_created_at", table_name="document_chunks")
    op.drop_index("ix_document_chunks_content_hash", table_name="document_chunks")
    op.drop_index("ix_document_chunks_document_id", table_name="document_chunks")
    op.drop_table("document_chunks")
    op.drop_column("documents", "rag_indexed_at")
    op.drop_column("documents", "rag_index_error")
    op.drop_column("documents", "rag_index_status")
