"""Read-only natural language SQL agent orchestration."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppError
from app.services.sql_execution import execute_readonly_sql
from app.services.sql_generator import SQLGenerator, get_default_sql_generator
from app.services.sql_guard import validate_readonly_sql
from app.services.sql_schema import get_business_schema


logger = logging.getLogger(__name__)


class SqlAgentService:
    def __init__(
        self,
        db: Session,
        generator: SQLGenerator | None = None,
    ) -> None:
        self.db = db
        self.generator = generator or get_default_sql_generator()

    def ask(self, question: str, max_rows: int | None = None) -> dict[str, Any]:
        cleaned = (question or "").strip()
        logger.info("SQL agent question received length=%s", len(cleaned))

        if not cleaned:
            return self._response(
                question=cleaned,
                answer="Please enter a business data question.",
                status="unsupported",
            )

        if len(cleaned) > settings.SQL_MAX_QUESTION_LENGTH:
            return self._response(
                question=cleaned,
                answer=(
                    f"Question exceeds the maximum length of "
                    f"{settings.SQL_MAX_QUESTION_LENGTH} characters."
                ),
                status="invalid_query",
            )

        schema = get_business_schema()
        try:
            generation = self.generator.generate_sql(cleaned, schema)
        except AppError as exc:
            logger.warning("SQL generation failed: %s", exc.message)
            return self._response(
                question=cleaned,
                answer="I couldn't safely generate a query for that question.",
                status="invalid_query",
            )
        except Exception:
            logger.exception("Unexpected SQL generation failure")
            return self._response(
                question=cleaned,
                answer="I couldn't safely generate a query for that question.",
                status="invalid_query",
            )

        if generation.status != "ready" or not generation.sql:
            return self._response(
                question=cleaned,
                answer=generation.detail
                or "I cannot answer this question using the available business data.",
                status="unsupported",
            )

        logger.info("SQL agent generated SQL length=%s", len(generation.sql))
        validation = validate_readonly_sql(generation.sql)
        if not validation.valid or not validation.normalized_sql:
            logger.warning("SQL agent validation rejected query: %s", validation.reason)
            return self._response(
                question=cleaned,
                sql=generation.sql,
                answer="I couldn't safely generate a query for that question.",
                status="invalid_query",
            )

        try:
            execution = execute_readonly_sql(
                self.db,
                validation.normalized_sql,
                max_rows=max_rows,
            )
        except AppError:
            return self._response(
                question=cleaned,
                sql=validation.normalized_sql,
                answer="I couldn't answer that question using the available business data.",
                status="execution_error",
            )
        except Exception:
            logger.exception("SQL agent unexpected execution failure")
            return self._response(
                question=cleaned,
                sql=validation.normalized_sql,
                answer="I couldn't answer that question using the available business data.",
                status="execution_error",
            )

        answer = build_human_answer(cleaned, execution.columns, execution.rows)
        logger.info(
            "SQL agent success row_count=%s duration_ms=%s",
            execution.row_count,
            execution.duration_ms,
        )
        return self._response(
            question=cleaned,
            sql=validation.normalized_sql,
            columns=execution.columns,
            rows=execution.rows,
            row_count=execution.row_count,
            answer=answer,
            status="success",
        )

    @staticmethod
    def _response(
        *,
        question: str,
        answer: str,
        status: str,
        sql: str | None = None,
        columns: list[str] | None = None,
        rows: list[dict[str, Any]] | None = None,
        row_count: int = 0,
    ) -> dict[str, Any]:
        return {
            "question": question,
            "answer": answer,
            "sql": sql,
            "columns": columns or [],
            "rows": rows or [],
            "row_count": row_count,
            "status": status,
        }


def build_human_answer(
    question: str,
    columns: list[str],
    rows: list[dict[str, Any]],
) -> str:
    """Build a concise answer strictly from SQL result values."""
    if not rows:
        return "No matching business records were found for that question."

    amount_column = next(
        (
            column
            for column in columns
            if any(token in column.lower() for token in ("total", "amount", "sum"))
        ),
        None,
    )
    currency_column = next(
        (column for column in columns if "currency" in column.lower()),
        None,
    )

    vendor_column = next((column for column in columns if "vendor" in column.lower()), None)
    if vendor_column and amount_column:
        parts = []
        for row in rows:
            part = f"{row.get(vendor_column) or 'Unknown'}: {row.get(amount_column)}"
            if currency_column:
                part += f" {row.get(currency_column) or ''}".rstrip()
            parts.append(part)
        shown = parts[:10]
        more = f" (+{len(parts) - len(shown)} more in the table)" if len(parts) > len(shown) else ""
        return "Invoice totals by vendor: " + "; ".join(shown) + more + "."

    if currency_column and amount_column and len(rows) >= 1:
        parts = [
            f"{row.get(currency_column) or 'Unknown'}: {row.get(amount_column)}"
            for row in rows
        ]
        if len(parts) == 1:
            currency_label, amount_label = [part.strip() for part in parts[0].split(":", 1)]
            return f"The total invoice amount for {currency_label} is {amount_label}."
        return (
            "Invoice totals by currency (currencies are not combined): "
            + "; ".join(parts)
            + "."
        )

    if len(rows) == 1 and len(columns) == 1:
        key = columns[0]
        value = rows[0].get(key)
        label = key.replace("_", " ")
        q = question.lower()
        if "how many" in q or key.endswith("_count") or "count" in key:
            return _count_sentence(question, key, value)
        if "total" in key or "amount" in key or "sum" in key:
            return f"The {label} is {value}."
        return f"The result for {label} is {value}."

    if len(rows) == 1:
        parts = [f"{column.replace('_', ' ')}: {rows[0].get(column)}" for column in columns]
        return "Result — " + "; ".join(parts) + "."

    return f"Found {len(rows)} matching rows. See the result table for details."


def _count_sentence(question: str, key: str, value: Any) -> str:
    q = question.lower()
    if "invoice" in key or "invoice" in q:
        return f"There are {value} invoices in the system."
    if "purchase_order" in key or "purchase order" in q:
        return f"There are {value} purchase orders in the system."
    if "vendor" in key or "vendor" in q:
        return f"There are {value} vendors registered."
    if "mismatch" in key or "mismatch" in q:
        return f"There are {value} validation mismatches."
    if "document" in key or "document" in q:
        return f"There are {value} documents."
    if "review" in key or "review" in q:
        return f"There are {value} review items."
    if "chunk" in key:
        return f"There are {value} indexed document chunks."
    label = key.replace("_", " ")
    return f"There are {value} {label}."


def validate_sql_only(sql: str) -> dict[str, Any]:
    result = validate_readonly_sql(sql)
    return {
        "valid": result.valid,
        "reason": None if result.valid else (result.reason or "Only read-only SELECT queries are allowed."),
    }
