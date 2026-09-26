"""Alembic revision: add document classification fields."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260324_0003"
down_revision: str | None = "20260324_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("document_type", sa.String(length=50), nullable=True))
    op.add_column("documents", sa.Column("classification_confidence", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "classification_confidence")
    op.drop_column("documents", "document_type")
