"""Alembic revision: create workflow automation tables."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260324_0011"
down_revision: str | None = "20260324_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workflows",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("trigger_type", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_workflows_trigger_type", "workflows", ["trigger_type"], unique=False)
    op.create_index("ix_workflows_status", "workflows", ["status"], unique=False)
    op.create_index("ix_workflows_created_at", "workflows", ["created_at"], unique=False)

    op.create_table(
        "workflow_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workflow_id", sa.Uuid(), nullable=False),
        sa.Column("trigger_event", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=100), nullable=False),
        sa.Column("entity_id", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("execution_metadata", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_workflow_executions_workflow_id",
        "workflow_executions",
        ["workflow_id"],
        unique=False,
    )
    op.create_index(
        "ix_workflow_executions_status",
        "workflow_executions",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_workflow_executions_entity",
        "workflow_executions",
        ["entity_type", "entity_id"],
        unique=False,
    )
    op.create_index(
        "ix_workflow_executions_started_at",
        "workflow_executions",
        ["started_at"],
        unique=False,
    )
    op.create_index(
        "ix_workflow_executions_trigger_event",
        "workflow_executions",
        ["trigger_event"],
        unique=False,
    )

    op.create_table(
        "workflow_step_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workflow_execution_id", sa.Uuid(), nullable=False),
        sa.Column("step_name", sa.String(length=255), nullable=False),
        sa.Column("step_type", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["workflow_execution_id"],
            ["workflow_executions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_workflow_step_executions_execution_id",
        "workflow_step_executions",
        ["workflow_execution_id"],
        unique=False,
    )
    op.create_index(
        "ix_workflow_step_executions_status",
        "workflow_step_executions",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_workflow_step_executions_started_at",
        "workflow_step_executions",
        ["started_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_workflow_step_executions_started_at", table_name="workflow_step_executions")
    op.drop_index("ix_workflow_step_executions_status", table_name="workflow_step_executions")
    op.drop_index("ix_workflow_step_executions_execution_id", table_name="workflow_step_executions")
    op.drop_table("workflow_step_executions")
    op.drop_index("ix_workflow_executions_trigger_event", table_name="workflow_executions")
    op.drop_index("ix_workflow_executions_started_at", table_name="workflow_executions")
    op.drop_index("ix_workflow_executions_entity", table_name="workflow_executions")
    op.drop_index("ix_workflow_executions_status", table_name="workflow_executions")
    op.drop_index("ix_workflow_executions_workflow_id", table_name="workflow_executions")
    op.drop_table("workflow_executions")
    op.drop_index("ix_workflows_created_at", table_name="workflows")
    op.drop_index("ix_workflows_status", table_name="workflows")
    op.drop_index("ix_workflows_trigger_type", table_name="workflows")
    op.drop_table("workflows")
