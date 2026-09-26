"""Controlled business schema exposed to the read-only SQL agent."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    data_type: str
    description: str


@dataclass(frozen=True)
class RelationshipInfo:
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    description: str


@dataclass(frozen=True)
class TableInfo:
    name: str
    description: str
    columns: tuple[ColumnInfo, ...]


BUSINESS_TABLES: tuple[TableInfo, ...] = (
    TableInfo(
        name="documents",
        description="Uploaded business documents and processing metadata.",
        columns=(
            ColumnInfo("id", "uuid", "Document primary key"),
            ColumnInfo("original_filename", "string", "Original uploaded filename"),
            ColumnInfo("file_type", "string", "File extension/type"),
            ColumnInfo("file_size", "integer", "File size in bytes"),
            ColumnInfo("status", "string", "uploaded|processing|processed|failed|manual_review"),
            ColumnInfo("uploaded_at", "datetime", "Upload timestamp (UTC)"),
            ColumnInfo("processed_at", "datetime", "Processing completion timestamp"),
            ColumnInfo("document_type", "string", "invoice|purchase_order|contract|receipt|bank_statement|other"),
            ColumnInfo("classification_confidence", "float", "Classification confidence score"),
            ColumnInfo("rag_index_status", "string", "RAG indexing status"),
            ColumnInfo("rag_indexed_at", "datetime", "Last RAG index timestamp"),
        ),
    ),
    TableInfo(
        name="invoices",
        description="Extracted invoice records linked to documents and vendors.",
        columns=(
            ColumnInfo("id", "uuid", "Invoice primary key"),
            ColumnInfo("document_id", "uuid", "Related document id"),
            ColumnInfo("vendor_id", "uuid", "Linked vendor id"),
            ColumnInfo("vendor_name", "string", "Vendor name extracted from the invoice"),
            ColumnInfo("invoice_number", "string", "Invoice number"),
            ColumnInfo("invoice_date", "date", "Invoice date"),
            ColumnInfo("subtotal", "numeric", "Invoice subtotal"),
            ColumnInfo("tax_amount", "numeric", "Invoice tax amount"),
            ColumnInfo("total_amount", "numeric", "Invoice total amount"),
            ColumnInfo("currency", "string", "Currency code"),
            ColumnInfo("extraction_confidence", "float", "Extraction confidence"),
            ColumnInfo("created_at", "datetime", "Record created at"),
        ),
    ),
    TableInfo(
        name="purchase_orders",
        description="Extracted purchase order records.",
        columns=(
            ColumnInfo("id", "uuid", "Purchase order primary key"),
            ColumnInfo("document_id", "uuid", "Related document id"),
            ColumnInfo("vendor_id", "uuid", "Linked vendor id"),
            ColumnInfo("po_number", "string", "Purchase order number"),
            ColumnInfo("vendor_name", "string", "Vendor name on the PO"),
            ColumnInfo("po_date", "date", "Purchase order date"),
            ColumnInfo("subtotal", "numeric", "PO subtotal"),
            ColumnInfo("tax_amount", "numeric", "PO tax amount"),
            ColumnInfo("total_amount", "numeric", "PO total amount"),
            ColumnInfo("currency", "string", "Currency code"),
            ColumnInfo("extraction_confidence", "float", "Extraction confidence"),
            ColumnInfo("created_at", "datetime", "Record created at"),
        ),
    ),
    TableInfo(
        name="vendors",
        description="Normalized vendor master records.",
        columns=(
            ColumnInfo("id", "uuid", "Vendor primary key"),
            ColumnInfo("name", "string", "Vendor display name"),
            ColumnInfo("normalized_name", "string", "Normalized unique vendor name"),
            ColumnInfo("email", "string", "Vendor email"),
            ColumnInfo("phone", "string", "Vendor phone"),
            ColumnInfo("created_at", "datetime", "Vendor created at"),
        ),
    ),
    TableInfo(
        name="document_validations",
        description="Invoice vs purchase-order validation results.",
        columns=(
            ColumnInfo("id", "uuid", "Validation primary key"),
            ColumnInfo("invoice_id", "uuid", "Related invoice id"),
            ColumnInfo("purchase_order_id", "uuid", "Related purchase order id"),
            ColumnInfo("status", "string", "matched|mismatch|needs_review"),
            ColumnInfo("vendor_match", "boolean", "Whether vendors matched"),
            ColumnInfo("currency_match", "boolean", "Whether currencies matched"),
            ColumnInfo("subtotal_match", "boolean", "Whether subtotals matched"),
            ColumnInfo("tax_match", "boolean", "Whether tax amounts matched"),
            ColumnInfo("total_match", "boolean", "Whether totals matched"),
            ColumnInfo("invoice_number", "string", "Invoice number snapshot"),
            ColumnInfo("po_number", "string", "PO number snapshot"),
            ColumnInfo("created_at", "datetime", "Validation created at"),
        ),
    ),
    TableInfo(
        name="document_reviews",
        description="Human review queue items for documents needing attention.",
        columns=(
            ColumnInfo("id", "uuid", "Review primary key"),
            ColumnInfo("document_id", "uuid", "Related document id"),
            ColumnInfo("status", "string", "pending|in_review|approved|rejected"),
            ColumnInfo("priority", "string", "high|medium|low"),
            ColumnInfo("reason", "string", "Review reason code"),
            ColumnInfo("created_at", "datetime", "Review created at"),
            ColumnInfo("resolved_at", "datetime", "Review resolved at"),
        ),
    ),
    TableInfo(
        name="document_chunks",
        description="Indexed text chunks used by the RAG assistant (no embeddings).",
        columns=(
            ColumnInfo("id", "uuid", "Chunk primary key"),
            ColumnInfo("document_id", "uuid", "Related document id"),
            ColumnInfo("chunk_index", "integer", "Chunk order within the document"),
            ColumnInfo("character_count", "integer", "Chunk character count"),
            ColumnInfo("created_at", "datetime", "Chunk created at"),
        ),
    ),
)

BUSINESS_RELATIONSHIPS: tuple[RelationshipInfo, ...] = (
    RelationshipInfo("invoices", "document_id", "documents", "id", "Invoice belongs to a document"),
    RelationshipInfo("invoices", "vendor_id", "vendors", "id", "Invoice may link to a vendor"),
    RelationshipInfo("purchase_orders", "document_id", "documents", "id", "PO belongs to a document"),
    RelationshipInfo("purchase_orders", "vendor_id", "vendors", "id", "PO may link to a vendor"),
    RelationshipInfo("document_validations", "invoice_id", "invoices", "id", "Validation references invoice"),
    RelationshipInfo(
        "document_validations",
        "purchase_order_id",
        "purchase_orders",
        "id",
        "Validation references purchase order",
    ),
    RelationshipInfo("document_reviews", "document_id", "documents", "id", "Review belongs to a document"),
    RelationshipInfo("document_chunks", "document_id", "documents", "id", "Chunk belongs to a document"),
)

ALLOWED_TABLES: frozenset[str] = frozenset(table.name for table in BUSINESS_TABLES)
ALLOWED_COLUMNS_BY_TABLE: dict[str, frozenset[str]] = {
    table.name: frozenset(column.name for column in table.columns) for table in BUSINESS_TABLES
}


def get_business_schema() -> dict[str, object]:
    """Return a JSON-serializable controlled schema for SQL generation."""
    return {
        "tables": [
            {
                "name": table.name,
                "description": table.description,
                "columns": [
                    {
                        "name": column.name,
                        "type": column.data_type,
                        "description": column.description,
                    }
                    for column in table.columns
                ],
            }
            for table in BUSINESS_TABLES
        ],
        "relationships": [
            {
                "from_table": rel.from_table,
                "from_column": rel.from_column,
                "to_table": rel.to_table,
                "to_column": rel.to_column,
                "description": rel.description,
            }
            for rel in BUSINESS_RELATIONSHIPS
        ],
    }


def schema_prompt_text() -> str:
    """Compact schema text for generator prompts."""
    lines: list[str] = ["Allowed business tables and columns:"]
    for table in BUSINESS_TABLES:
        cols = ", ".join(f"{column.name} ({column.data_type})" for column in table.columns)
        lines.append(f"- {table.name}: {cols}")
        lines.append(f"  ({table.description})")
    lines.append("Relationships:")
    for rel in BUSINESS_RELATIONSHIPS:
        lines.append(
            f"- {rel.from_table}.{rel.from_column} -> {rel.to_table}.{rel.to_column} ({rel.description})"
        )
    return "\n".join(lines)
