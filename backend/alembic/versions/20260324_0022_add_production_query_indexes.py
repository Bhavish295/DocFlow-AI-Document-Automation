"""Alembic revision: useful production query indexes (Step 26)."""

from collections.abc import Sequence

from alembic import op


revision: str = "20260324_0022"
down_revision: str | None = "20260324_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Validations — filter/list by status and time
    op.create_index(
        "ix_document_validations_status",
        "document_validations",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_document_validations_created_at",
        "document_validations",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_document_validations_invoice_id",
        "document_validations",
        ["invoice_id"],
        unique=False,
    )
    op.create_index(
        "ix_document_validations_purchase_order_id",
        "document_validations",
        ["purchase_order_id"],
        unique=False,
    )

    # Invoices / POs — lookup by business numbers and created_at
    op.create_index("ix_invoices_invoice_number", "invoices", ["invoice_number"], unique=False)
    op.create_index("ix_invoices_created_at", "invoices", ["created_at"], unique=False)
    op.create_index("ix_purchase_orders_po_number", "purchase_orders", ["po_number"], unique=False)
    op.create_index(
        "ix_purchase_orders_created_at",
        "purchase_orders",
        ["created_at"],
        unique=False,
    )

    # Composite helpful for document list filters
    op.create_index(
        "ix_documents_status_uploaded_at",
        "documents",
        ["status", "uploaded_at"],
        unique=False,
    )
    op.create_index(
        "ix_documents_document_type_uploaded_at",
        "documents",
        ["document_type", "uploaded_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_documents_document_type_uploaded_at", table_name="documents")
    op.drop_index("ix_documents_status_uploaded_at", table_name="documents")
    op.drop_index("ix_purchase_orders_created_at", table_name="purchase_orders")
    op.drop_index("ix_purchase_orders_po_number", table_name="purchase_orders")
    op.drop_index("ix_invoices_created_at", table_name="invoices")
    op.drop_index("ix_invoices_invoice_number", table_name="invoices")
    op.drop_index("ix_document_validations_purchase_order_id", table_name="document_validations")
    op.drop_index("ix_document_validations_invoice_id", table_name="document_validations")
    op.drop_index("ix_document_validations_created_at", table_name="document_validations")
    op.drop_index("ix_document_validations_status", table_name="document_validations")
