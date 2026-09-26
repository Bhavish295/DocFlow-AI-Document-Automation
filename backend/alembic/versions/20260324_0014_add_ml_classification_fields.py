"""Alembic revision: ML-assisted classification evidence fields on documents."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260324_0014"
down_revision: str | None = "20260324_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("rule_based_document_type", sa.String(length=50), nullable=True))
    op.add_column(
        "documents",
        sa.Column("rule_based_classification_confidence", sa.Float(), nullable=True),
    )
    op.add_column("documents", sa.Column("ml_document_type", sa.String(length=50), nullable=True))
    op.add_column("documents", sa.Column("ml_classification_confidence", sa.Float(), nullable=True))
    op.add_column("documents", sa.Column("classification_method", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "classification_method")
    op.drop_column("documents", "ml_classification_confidence")
    op.drop_column("documents", "ml_document_type")
    op.drop_column("documents", "rule_based_classification_confidence")
    op.drop_column("documents", "rule_based_document_type")
