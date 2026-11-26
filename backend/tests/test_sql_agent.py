"""Tests for the read-only natural language SQL agent (Step 11)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.models.document import Document, DocumentStatus
from app.models.invoice import Invoice
from app.models.purchase_order import PurchaseOrder
from app.models.validation import DocumentValidation, ValidationStatus
from app.models.vendor import Vendor
from app.services.sql_generator import DeterministicSQLGenerator
from app.services.sql_guard import validate_readonly_sql
from app.services.sql_schema import ALLOWED_TABLES, get_business_schema


def _seed_business_data(session_factory):
    db = session_factory()
    try:
        vendor = Vendor(name="ABC Traders", normalized_name="abc traders")
        db.add(vendor)
        db.flush()

        doc_inv = Document(
            original_filename="inv.pdf",
            stored_filename=f"{uuid.uuid4()}.pdf",
            file_type="pdf",
            file_size=100,
            storage_path="storage/uploads/inv.pdf",
            status=DocumentStatus.PROCESSED.value,
            document_type="invoice",
            uploaded_at=datetime.now(timezone.utc),
        )
        doc_po = Document(
            original_filename="po.pdf",
            stored_filename=f"{uuid.uuid4()}.pdf",
            file_type="pdf",
            file_size=120,
            storage_path="storage/uploads/po.pdf",
            status=DocumentStatus.PROCESSED.value,
            document_type="purchase_order",
            uploaded_at=datetime.now(timezone.utc),
        )
        db.add_all([doc_inv, doc_po])
        db.flush()

        invoice = Invoice(
            document_id=doc_inv.id,
            vendor_id=vendor.id,
            vendor_name="ABC Traders",
            invoice_number="INV-1",
            total_amount=250000,
            currency="PKR",
        )
        doc_inv2 = Document(
            original_filename="inv2.pdf",
            stored_filename=f"{uuid.uuid4()}.pdf",
            file_type="pdf",
            file_size=110,
            storage_path="storage/uploads/inv2.pdf",
            status=DocumentStatus.PROCESSED.value,
            document_type="invoice",
            uploaded_at=datetime.now(timezone.utc),
        )
        db.add(doc_inv2)
        db.flush()
        invoice_high = Invoice(
            document_id=doc_inv2.id,
            vendor_id=vendor.id,
            vendor_name="ABC Traders",
            invoice_number="INV-2",
            total_amount=150000,
            currency="PKR",
        )

        po = PurchaseOrder(
            document_id=doc_po.id,
            vendor_id=vendor.id,
            vendor_name="ABC Traders",
            po_number="PO-1",
            total_amount=250000,
            currency="PKR",
        )
        db.add_all([invoice, invoice_high, po])
        db.flush()

        validation = DocumentValidation(
            invoice_id=invoice.id,
            purchase_order_id=po.id,
            status=ValidationStatus.MISMATCH.value,
            total_match=False,
            mismatch_summary="Total mismatch",
        )
        db.add(validation)
        db.commit()
        return {
            "vendor_id": vendor.id,
            "invoice_count": 2,
            "po_count": 1,
            "mismatch_count": 1,
        }
    finally:
        db.close()


def test_sql_guard_allows_select():
    result = validate_readonly_sql("SELECT COUNT(*) AS invoice_count FROM invoices")
    assert result.valid is True
    assert result.normalized_sql is not None


def test_sql_guard_allows_aggregate_and_filter():
    result = validate_readonly_sql(
        "SELECT COALESCE(SUM(total_amount), 0) AS total_invoice_amount "
        "FROM invoices WHERE total_amount > 100"
    )
    assert result.valid is True


def test_sql_guard_allows_join():
    result = validate_readonly_sql(
        "SELECT v.name AS vendor_name FROM invoices i "
        "JOIN vendors v ON v.id = i.vendor_id"
    )
    assert result.valid is True


def test_sql_guard_rejects_unsafe_keywords():
    unsafe = [
        "INSERT INTO invoices (vendor_name) VALUES ('x')",
        "UPDATE invoices SET total_amount = 1",
        "DELETE FROM invoices",
        "DROP TABLE invoices",
        "ALTER TABLE invoices ADD COLUMN x INT",
        "TRUNCATE TABLE invoices",
        "CREATE TABLE hack (id INT)",
        "GRANT ALL ON invoices TO public",
        "REVOKE ALL ON invoices FROM public",
        "SELECT * FROM invoices; DELETE FROM invoices",
        "SELECT 1 -- comment\nFROM invoices",
        "SELECT 1 /* bypass */ FROM invoices",
        "",
        "   ",
        "SHOW TABLES",
        "EXPLAIN SELECT 1 FROM invoices",
    ]
    for sql in unsafe:
        result = validate_readonly_sql(sql)
        assert result.valid is False, sql


def test_sql_guard_rejects_unknown_table_and_column():
    bad_table = validate_readonly_sql("SELECT id FROM secrets")
    assert bad_table.valid is False
    assert "table" in (bad_table.reason or "").lower()

    bad_column = validate_readonly_sql("SELECT password FROM invoices")
    assert bad_column.valid is False


def test_sql_guard_rejects_max_query_length(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "SQL_MAX_QUERY_LENGTH", 20)
    result = validate_readonly_sql("SELECT COUNT(*) AS invoice_count FROM invoices")
    assert result.valid is False
    assert "maximum length" in (result.reason or "").lower()


def test_schema_exposure_is_controlled():
    schema = get_business_schema()
    names = {table["name"] for table in schema["tables"]}
    assert names == set(ALLOWED_TABLES)
    assert "documents" in names
    assert "invoices" in names
    assert "pg_catalog" not in names
    invoice_cols = next(t["columns"] for t in schema["tables"] if t["name"] == "invoices")
    col_names = {c["name"] for c in invoice_cols}
    assert "total_amount" in col_names
    assert "embedding" not in col_names


def test_deterministic_sql_generation_common_questions():
    gen = DeterministicSQLGenerator()
    cases = [
        ("How many invoices do we have?", "invoices"),
        ("How many purchase orders exist?", "purchase_orders"),
        ("How many vendors are registered?", "vendors"),
        ("How many validation mismatches are there?", "document_validations"),
        ("What is the total invoice amount?", "SUM(total_amount)"),
        ("What is the total invoice value in the system?", "GROUP BY currency"),
        ("What is the sum of invoice totals?", "SUM(total_amount)"),
        ("What is the total amount of all invoices?", "SUM(total_amount)"),
        ("How much are all invoices worth?", "SUM(total_amount)"),
        ("What is the total invoice value for PKR?", "PKR"),
        ("Show invoice totals by vendor.", "GROUP BY vendor_name"),
        ("What is the total invoice amount by vendor?", "GROUP BY vendor_name, currency"),
        ("Total invoice value per vendor", "GROUP BY vendor_name"),
        ("Show vendor-wise invoice totals", "GROUP BY vendor_name"),
        ("Which vendors have invoices?", "JOIN"),
        ("How many invoices are above 100000?", "total_amount > 100000"),
    ]
    for question, expected_fragment in cases:
        result = gen.generate_sql(question)
        assert result.status == "ready", question
        assert result.sql is not None
        assert expected_fragment.lower() in result.sql.lower()


def test_invoice_total_sql_does_not_mix_currencies():
    gen = DeterministicSQLGenerator()
    result = gen.generate_sql("What is the total invoice value in the system?")
    assert result.status == "ready"
    sql = (result.sql or "").lower()
    assert "sum(total_amount)" in sql
    assert "group by currency" in sql
    assert "where" not in sql or "currency" in sql

    pkr = gen.generate_sql("What is the total invoice value for PKR?")
    assert pkr.status == "ready"
    pkr_sql = (pkr.sql or "").lower()
    assert "sum(total_amount)" in pkr_sql
    assert "pkr" in pkr_sql
    assert "group by" not in pkr_sql


def test_deterministic_unsupported_question():
    gen = DeterministicSQLGenerator()
    result = gen.generate_sql("What will the stock market do tomorrow?")
    assert result.status == "unsupported"
    assert result.sql is None


def test_sql_validate_api(client):
    ok = client.post("/api/v1/sql/validate", json={"sql": "SELECT COUNT(*) FROM invoices"})
    assert ok.status_code == 200
    assert ok.json()["valid"] is True

    bad = client.post("/api/v1/sql/validate", json={"sql": "DELETE FROM invoices"})
    assert bad.status_code == 200
    payload = bad.json()
    assert payload["valid"] is False
    assert "read-only" in payload["reason"].lower() or "select" in payload["reason"].lower()


def test_sql_ask_api_success(client):
    _seed_business_data(client.testing_session_local)
    response = client.post(
        "/api/v1/sql/ask",
        json={"question": "How many invoices do we have?"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["sql"]
    assert "SELECT" in payload["sql"].upper()
    assert payload["row_count"] == 1
    assert payload["rows"][0]["invoice_count"] == 2
    assert "2" in payload["answer"]


def test_sql_ask_aggregates_and_filters(client):
    _seed_business_data(client.testing_session_local)

    total = client.post(
        "/api/v1/sql/ask",
        json={"question": "What is the total invoice amount?"},
    ).json()
    assert total["status"] == "success"
    assert total["row_count"] == 1
    assert total["rows"][0]["currency"] == "PKR"
    assert float(total["rows"][0]["total_invoice_amount"]) == 400000.0

    value_q = client.post(
        "/api/v1/sql/ask",
        json={"question": "What is the total invoice value in the system?"},
    ).json()
    assert value_q["status"] == "success"
    assert value_q["row_count"] == 1
    assert float(value_q["rows"][0]["total_invoice_amount"]) == 400000.0

    pkr = client.post(
        "/api/v1/sql/ask",
        json={"question": "What is the total invoice value for PKR?"},
    ).json()
    assert pkr["status"] == "success"
    assert float(pkr["rows"][0]["total_invoice_amount"]) == 400000.0

    above = client.post(
        "/api/v1/sql/ask",
        json={"question": "How many invoices are above 100000?"},
    ).json()
    assert above["status"] == "success"
    assert above["rows"][0]["invoice_count"] == 2

    mismatches = client.post(
        "/api/v1/sql/ask",
        json={"question": "How many validation mismatches are there?"},
    ).json()
    assert mismatches["status"] == "success"
    assert mismatches["rows"][0]["mismatch_count"] == 1

    vendors = client.post(
        "/api/v1/sql/ask",
        json={"question": "How many vendors are registered?"},
    ).json()
    assert vendors["status"] == "success"
    assert vendors["rows"][0]["vendor_count"] == 1

    pos = client.post(
        "/api/v1/sql/ask",
        json={"question": "How many purchase orders exist?"},
    ).json()
    assert pos["status"] == "success"
    assert pos["rows"][0]["purchase_order_count"] == 1


def test_sql_ask_invoice_totals_do_not_mix_currencies(client):
    db = client.testing_session_local()
    try:
        vendor = Vendor(name="Multi FX Co", normalized_name="multi fx co")
        db.add(vendor)
        db.flush()
        docs = []
        for name, amount, currency in [
            ("inv-pkr.pdf", 531000, "PKR"),
            ("inv-usd.pdf", 1000, "USD"),
        ]:
            doc = Document(
                original_filename=name,
                stored_filename=f"{uuid.uuid4()}.pdf",
                file_type="pdf",
                file_size=100,
                storage_path=f"storage/uploads/{name}",
                status=DocumentStatus.PROCESSED.value,
                document_type="invoice",
                uploaded_at=datetime.now(timezone.utc),
            )
            db.add(doc)
            db.flush()
            docs.append(doc)
            db.add(
                Invoice(
                    document_id=doc.id,
                    vendor_id=vendor.id,
                    vendor_name=vendor.name,
                    invoice_number=f"INV-{currency}",
                    total_amount=amount,
                    currency=currency,
                )
            )
        db.commit()
    finally:
        db.close()

    response = client.post(
        "/api/v1/sql/ask",
        json={"question": "What is the total amount of all invoices?"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["row_count"] == 2
    by_currency = {
        row["currency"]: float(row["total_invoice_amount"]) for row in payload["rows"]
    }
    assert by_currency["PKR"] == 531000.0
    assert by_currency["USD"] == 1000.0
    assert "not combined" in payload["answer"].lower() or "currency" in payload["answer"].lower()

    # A single combined total must not be returned when currencies differ.
    assert not any(
        abs(float(row["total_invoice_amount"]) - 532000.0) < 0.01 for row in payload["rows"]
    )


def test_sql_ask_unsupported(client):
    response = client.post(
        "/api/v1/sql/ask",
        json={"question": "Delete all invoices from the database"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "unsupported"
    assert payload["sql"] is None
    assert payload["rows"] == []


def test_sql_ask_question_length_limit(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "SQL_MAX_QUESTION_LENGTH", 10)
    response = client.post(
        "/api/v1/sql/ask",
        json={"question": "How many invoices do we have in the system today?"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "invalid_query"


def test_sql_ask_row_limit(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "SQL_MAX_ROWS", 1)
    _seed_business_data(client.testing_session_local)
    response = client.post(
        "/api/v1/sql/ask",
        json={"question": "Which vendors have invoices?", "max_rows": 50},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["row_count"] <= 1


def test_sql_execution_never_runs_unsafe(client):
    """Guard must reject unsafe SQL before execution — validate endpoint does not execute."""
    response = client.post(
        "/api/v1/sql/validate",
        json={"sql": "DELETE FROM invoices; SELECT 1"},
    )
    assert response.status_code == 200
    assert response.json()["valid"] is False


def test_invalid_generated_sql_path(client, monkeypatch):
    class BadGenerator:
        def generate_sql(self, question, schema=None):
            from app.services.sql_generator import SqlGenerationResult

            return SqlGenerationResult(
                sql="DELETE FROM invoices",
                status="ready",
            )

    from app.services import sql_agent as sql_agent_module

    monkeypatch.setattr(
        sql_agent_module,
        "get_default_sql_generator",
        lambda: BadGenerator(),
    )
    response = client.post(
        "/api/v1/sql/ask",
        json={"question": "How many invoices?"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "invalid_query"
    assert payload["rows"] == []


def test_human_answer_names_vendors_for_per_vendor_totals():
    from app.services.sql_agent import build_human_answer

    answer = build_human_answer(
        "What is the total invoice amount by vendor?",
        ["vendor_name", "currency", "invoice_count", "invoice_total"],
        [
            {"vendor_name": "ABC Pvt Ltd", "currency": "PKR", "invoice_count": 2, "invoice_total": 1062000.0},
            {"vendor_name": "Acme", "currency": "USD", "invoice_count": 1, "invoice_total": 400.0},
        ],
    )
    assert "ABC Pvt Ltd: 1062000.0 PKR" in answer
    assert "Acme: 400.0 USD" in answer
