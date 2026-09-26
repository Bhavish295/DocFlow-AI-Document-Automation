"""Alembic revision: create anomaly detection tables."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260324_0012"
down_revision: str | None = "20260324_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "anomaly_model_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("model_version", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("trained_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("feature_count", sa.Integer(), nullable=False),
        sa.Column("model_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_anomaly_model_runs_status", "anomaly_model_runs", ["status"], unique=False)
    op.create_index(
        "ix_anomaly_model_runs_trained_at",
        "anomaly_model_runs",
        ["trained_at"],
        unique=False,
    )
    op.create_index(
        "ix_anomaly_model_runs_created_at",
        "anomaly_model_runs",
        ["created_at"],
        unique=False,
    )

    op.create_table(
        "document_anomalies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("model_run_id", sa.Uuid(), nullable=False),
        sa.Column("anomaly_score", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=True),
        sa.Column("feature_values", sa.JSON(), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["model_run_id"], ["anomaly_model_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id",
            "model_run_id",
            name="uq_document_anomalies_document_model_run",
        ),
    )
    op.create_index(
        "ix_document_anomalies_document_id",
        "document_anomalies",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        "ix_document_anomalies_model_run_id",
        "document_anomalies",
        ["model_run_id"],
        unique=False,
    )
    op.create_index(
        "ix_document_anomalies_status",
        "document_anomalies",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_document_anomalies_anomaly_score",
        "document_anomalies",
        ["anomaly_score"],
        unique=False,
    )
    op.create_index(
        "ix_document_anomalies_detected_at",
        "document_anomalies",
        ["detected_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_document_anomalies_detected_at", table_name="document_anomalies")
    op.drop_index("ix_document_anomalies_anomaly_score", table_name="document_anomalies")
    op.drop_index("ix_document_anomalies_status", table_name="document_anomalies")
    op.drop_index("ix_document_anomalies_model_run_id", table_name="document_anomalies")
    op.drop_index("ix_document_anomalies_document_id", table_name="document_anomalies")
    op.drop_table("document_anomalies")
    op.drop_index("ix_anomaly_model_runs_created_at", table_name="anomaly_model_runs")
    op.drop_index("ix_anomaly_model_runs_trained_at", table_name="anomaly_model_runs")
    op.drop_index("ix_anomaly_model_runs_status", table_name="anomaly_model_runs")
    op.drop_table("anomaly_model_runs")
