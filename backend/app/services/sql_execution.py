"""Safe read-only SQL execution for the SQL agent."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppError
from app.services.sql_guard import validate_readonly_sql

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SqlExecutionResult:
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    duration_ms: int


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _ensure_row_limit(sql: str, max_rows: int) -> str:
    """Wrap the validated SELECT so the model cannot bypass row limits."""
    capped = max(1, int(max_rows))
    return f"SELECT * FROM ({sql}) AS _sql_agent_q LIMIT {capped}"


def execute_readonly_sql(
    db: Session,
    sql: str,
    *,
    max_rows: int | None = None,
    timeout_seconds: int | None = None,
) -> SqlExecutionResult:
    """Validate then execute SQL in a read-only transaction with limits."""
    validation = validate_readonly_sql(sql)
    if not validation.valid or not validation.normalized_sql:
        raise AppError(
            validation.reason or "Only read-only SELECT queries are allowed.",
            status_code=400,
        )

    row_limit = max_rows if max_rows is not None else settings.SQL_MAX_ROWS
    row_limit = max(1, min(int(row_limit), settings.SQL_MAX_ROWS))
    timeout = timeout_seconds if timeout_seconds is not None else settings.SQL_QUERY_TIMEOUT_SECONDS
    safe_sql = _ensure_row_limit(validation.normalized_sql, row_limit)

    started = time.perf_counter()
    bind = db.get_bind()
    dialect = bind.dialect.name if bind is not None else ""

    try:
        if dialect == "postgresql":
            # Keep this path read-only without changing the app-wide engine.
            db.execute(text("SET TRANSACTION READ ONLY"))
            db.execute(text(f"SET LOCAL statement_timeout = '{int(timeout) * 1000}'"))

        result = db.execute(text(safe_sql))
        mapping_rows = result.mappings().all()
        columns = list(result.keys())
        rows = [{column: _json_safe(row[column]) for column in columns} for row in mapping_rows]
        # Never persist anything from the SQL-agent path.
        db.rollback()
    except AppError:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.warning("SQL agent execution failed: %s", type(exc).__name__)
        raise AppError(
            "I couldn't answer that question using the available business data.",
            status_code=400,
        ) from exc

    duration_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "SQL agent executed query successfully rows=%s duration_ms=%s",
        len(rows),
        duration_ms,
    )
    return SqlExecutionResult(
        columns=columns,
        rows=rows,
        row_count=len(rows),
        duration_ms=duration_ms,
    )
