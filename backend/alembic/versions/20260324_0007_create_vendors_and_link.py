"""Alembic revision: create vendors table and link invoices/POs."""

from collections.abc import Sequence
import re
import uuid
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision: str = "20260324_0007"
down_revision: str | None = "20260324_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _normalize_vendor_name(name: str | None) -> str | None:
    if name is None:
        return None
    text = str(name).strip().lower()
    if not text:
        return None
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def upgrade() -> None:
    op.create_table(
        "vendors",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("tax_id", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("normalized_name", name="uq_vendors_normalized_name"),
    )
    op.create_index("ix_vendors_normalized_name", "vendors", ["normalized_name"], unique=False)

    op.add_column("invoices", sa.Column("vendor_id", sa.Uuid(), nullable=True))
    op.create_index("ix_invoices_vendor_id", "invoices", ["vendor_id"], unique=False)
    op.create_foreign_key(
        "fk_invoices_vendor_id_vendors",
        "invoices",
        "vendors",
        ["vendor_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column("purchase_orders", sa.Column("vendor_id", sa.Uuid(), nullable=True))
    op.create_index("ix_purchase_orders_vendor_id", "purchase_orders", ["vendor_id"], unique=False)
    op.create_foreign_key(
        "fk_purchase_orders_vendor_id_vendors",
        "purchase_orders",
        "vendors",
        ["vendor_id"],
        ["id"],
        ondelete="SET NULL",
    )

    connection = op.get_bind()
    now = datetime.now(timezone.utc)
    vendor_by_normalized: dict[str, uuid.UUID] = {}

    invoice_rows = connection.execute(
        sa.text("SELECT id, vendor_name FROM invoices WHERE vendor_name IS NOT NULL")
    ).mappings().all()
    po_rows = connection.execute(
        sa.text("SELECT id, vendor_name FROM purchase_orders WHERE vendor_name IS NOT NULL")
    ).mappings().all()

    for row in [*invoice_rows, *po_rows]:
        display = (row["vendor_name"] or "").strip()
        normalized = _normalize_vendor_name(display)
        if not normalized or normalized in vendor_by_normalized:
            continue
        vendor_id = uuid.uuid4()
        connection.execute(
            sa.text(
                """
                INSERT INTO vendors (id, name, normalized_name, email, phone, address, tax_id, created_at, updated_at)
                VALUES (:id, :name, :normalized_name, NULL, NULL, NULL, NULL, :created_at, :updated_at)
                """
            ),
            {
                "id": vendor_id,
                "name": display,
                "normalized_name": normalized,
                "created_at": now,
                "updated_at": now,
            },
        )
        vendor_by_normalized[normalized] = vendor_id

    for row in invoice_rows:
        normalized = _normalize_vendor_name(row["vendor_name"])
        if not normalized:
            continue
        vendor_id = vendor_by_normalized.get(normalized)
        if vendor_id is None:
            continue
        connection.execute(
            sa.text("UPDATE invoices SET vendor_id = :vendor_id WHERE id = :id"),
            {"vendor_id": vendor_id, "id": row["id"]},
        )

    for row in po_rows:
        normalized = _normalize_vendor_name(row["vendor_name"])
        if not normalized:
            continue
        vendor_id = vendor_by_normalized.get(normalized)
        if vendor_id is None:
            continue
        connection.execute(
            sa.text("UPDATE purchase_orders SET vendor_id = :vendor_id WHERE id = :id"),
            {"vendor_id": vendor_id, "id": row["id"]},
        )


def downgrade() -> None:
    op.drop_constraint("fk_purchase_orders_vendor_id_vendors", "purchase_orders", type_="foreignkey")
    op.drop_index("ix_purchase_orders_vendor_id", table_name="purchase_orders")
    op.drop_column("purchase_orders", "vendor_id")

    op.drop_constraint("fk_invoices_vendor_id_vendors", "invoices", type_="foreignkey")
    op.drop_index("ix_invoices_vendor_id", table_name="invoices")
    op.drop_column("invoices", "vendor_id")

    op.drop_index("ix_vendors_normalized_name", table_name="vendors")
    op.drop_table("vendors")
