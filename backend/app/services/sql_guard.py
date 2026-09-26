"""Deterministic read-only SQL validation for the SQL agent."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.config import settings
from app.services.sql_schema import ALLOWED_COLUMNS_BY_TABLE, ALLOWED_TABLES


FORBIDDEN_KEYWORDS = frozenset(
    {
        "INSERT",
        "UPDATE",
        "DELETE",
        "DROP",
        "ALTER",
        "TRUNCATE",
        "CREATE",
        "GRANT",
        "REVOKE",
        "MERGE",
        "CALL",
        "EXEC",
        "EXECUTE",
        "COPY",
        "REPLACE",
        "ATTACH",
        "DETACH",
        "PRAGMA",
        "VACUUM",
        "REINDEX",
        "LOAD",
        "INSTALL",
        "BEGIN",
        "COMMIT",
        "ROLLBACK",
        "SAVEPOINT",
        "RELEASE",
        "LOCK",
        "UNLOCK",
        "LISTEN",
        "NOTIFY",
        "DO",
        "PERFORM",
        "SECURITY",
        "OWNER",
        "TRIGGER",
        "FUNCTION",
        "PROCEDURE",
        "LANGUAGE",
        "EXTENSION",
        "DATABASE",
        "SCHEMA",
        "TABLESPACE",
        "ROLE",
        "POLICY",
        "PUBLICATION",
        "SUBSCRIPTION",
        "INTO",
        "RETURNING",
        "SET",
        "RESET",
        "SHOW",
        "EXPLAIN",
        "ANALYZE",
        "PREPARE",
        "DEALLOCATE",
        "DECLARE",
        "FETCH",
        "OPEN",
        "CLOSE",
        "MOVE",
        "CLUSTER",
        "COMMENT",
        "REASSIGN",
        "REFRESH",
        "RENAME",
        "HANDLER",
        "IMPORT",
        "EXPORT",
    }
)

FORBIDDEN_IDENTIFIERS = frozenset(
    {
        "PG_CATALOG",
        "INFORMATION_SCHEMA",
        "PG_SLEEP",
        "PG_READ_FILE",
        "PG_WRITE_FILE",
        "LO_IMPORT",
        "LO_EXPORT",
        "DBLINK",
        "CURRENT_SETTING",
        "SET_CONFIG",
        "VERSION",
    }
)

SQL_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\"[^\"]+\"|'[^']*'|\d+(?:\.\d+)?|[^\s]", re.MULTILINE)
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class SqlValidationResult:
    valid: bool
    reason: str | None = None
    normalized_sql: str | None = None


def normalize_sql(sql: str) -> str:
    return " ".join((sql or "").strip().split())


def _strip_trailing_semicolon(sql: str) -> str:
    return sql.rstrip().rstrip(";").strip()


def _contains_comments(sql: str) -> bool:
    if "--" in sql:
        return True
    if "/*" in sql or "*/" in sql:
        return True
    return False


def _has_multiple_statements(sql: str) -> bool:
    stripped = _strip_trailing_semicolon(sql)
    # Semicolon anywhere after normalization means multiple statements.
    return ";" in stripped


def _tokenize(sql: str) -> list[str]:
    return SQL_TOKEN_RE.findall(sql)


def _is_string_literal(token: str) -> bool:
    return len(token) >= 2 and token[0] == "'" and token[-1] == "'"


def _is_quoted_identifier(token: str) -> bool:
    return len(token) >= 2 and token[0] == '"' and token[-1] == '"'


def _unquote_identifier(token: str) -> str:
    if _is_quoted_identifier(token):
        return token[1:-1]
    return token


def validate_readonly_sql(
    sql: str,
    *,
    max_length: int | None = None,
    enforce_schema: bool = True,
) -> SqlValidationResult:
    """Validate that SQL is a single safe read-only SELECT against allowed tables."""
    if sql is None or not str(sql).strip():
        return SqlValidationResult(valid=False, reason="SQL query is empty.")

    raw = str(sql)
    limit = max_length if max_length is not None else settings.SQL_MAX_QUERY_LENGTH
    if len(raw) > limit:
        return SqlValidationResult(
            valid=False,
            reason=f"SQL query exceeds the maximum length of {limit} characters.",
        )

    if _contains_comments(raw):
        return SqlValidationResult(
            valid=False,
            reason="SQL comments are not allowed.",
        )

    if _has_multiple_statements(raw):
        return SqlValidationResult(
            valid=False,
            reason="Only a single SQL statement is allowed.",
        )

    normalized = normalize_sql(_strip_trailing_semicolon(raw))
    upper = normalized.upper()

    if not (upper.startswith("SELECT") or upper.startswith("WITH")):
        return SqlValidationResult(
            valid=False,
            reason="Only read-only SELECT queries are allowed.",
        )

    if re.search(r"\bFOR\s+UPDATE\b", upper) or re.search(r"\bFOR\s+SHARE\b", upper):
        return SqlValidationResult(
            valid=False,
            reason="Locking clauses are not allowed.",
        )

    if re.search(r"\bINTO\b", upper):
        return SqlValidationResult(
            valid=False,
            reason="SELECT INTO and similar write-adjacent clauses are not allowed.",
        )

    tokens = _tokenize(normalized)
    keyword_tokens: list[str] = []
    for token in tokens:
        if _is_string_literal(token):
            continue
        if _is_quoted_identifier(token):
            ident = _unquote_identifier(token).upper()
            if ident in FORBIDDEN_IDENTIFIERS:
                return SqlValidationResult(
                    valid=False,
                    reason="Access to system or restricted identifiers is not allowed.",
                )
            continue
        if IDENTIFIER_RE.match(token):
            upper_token = token.upper()
            keyword_tokens.append(upper_token)
            if upper_token in FORBIDDEN_KEYWORDS:
                return SqlValidationResult(
                    valid=False,
                    reason="Only read-only SELECT queries are allowed.",
                )
            if upper_token in FORBIDDEN_IDENTIFIERS:
                return SqlValidationResult(
                    valid=False,
                    reason="Access to system or restricted identifiers is not allowed.",
                )

    if "SELECT" not in keyword_tokens:
        return SqlValidationResult(
            valid=False,
            reason="Only read-only SELECT queries are allowed.",
        )

    if enforce_schema:
        schema_result = _validate_allowed_schema(normalized, tokens)
        if not schema_result.valid:
            return schema_result

    return SqlValidationResult(valid=True, reason=None, normalized_sql=normalized)


def _validate_allowed_schema(sql: str, tokens: list[str]) -> SqlValidationResult:
    """Ensure referenced tables/columns are in the controlled business schema."""
    lower_tokens: list[str] = []
    for token in tokens:
        if _is_string_literal(token):
            lower_tokens.append(token)
        elif _is_quoted_identifier(token):
            lower_tokens.append(_unquote_identifier(token).lower())
        elif IDENTIFIER_RE.match(token):
            lower_tokens.append(token.lower())
        else:
            lower_tokens.append(token)

    sql_keywords = {
        "select",
        "from",
        "where",
        "and",
        "or",
        "not",
        "null",
        "as",
        "on",
        "join",
        "left",
        "right",
        "inner",
        "outer",
        "full",
        "cross",
        "group",
        "by",
        "order",
        "asc",
        "desc",
        "limit",
        "offset",
        "count",
        "sum",
        "avg",
        "min",
        "max",
        "coalesce",
        "distinct",
        "case",
        "when",
        "then",
        "else",
        "end",
        "like",
        "ilike",
        "in",
        "is",
        "between",
        "true",
        "false",
        "with",
        "having",
        "union",
        "all",
        "cast",
        "date",
        "extract",
        "current_date",
        "current_timestamp",
        "now",
    }

    referenced_tables: set[str] = set()
    i = 0
    while i < len(lower_tokens):
        token = lower_tokens[i]
        if token in {"from", "join"} and i + 1 < len(lower_tokens):
            table = lower_tokens[i + 1]
            if table != "(" and IDENTIFIER_RE.match(table or "") and table not in sql_keywords:
                if table not in ALLOWED_TABLES:
                    return SqlValidationResult(
                        valid=False,
                        reason=f"Unknown or disallowed table(s): {table}.",
                    )
                referenced_tables.add(table)
        i += 1

    if not referenced_tables:
        return SqlValidationResult(
            valid=False,
            reason="Query must reference an allowed business table.",
        )

    for match in re.finditer(r"\b([a-z_][a-z0-9_]*)\s*\.\s*([a-z_][a-z0-9_]*)\b", sql.lower()):
        table_part, column_part = match.group(1), match.group(2)
        if table_part in ALLOWED_TABLES and column_part not in ALLOWED_COLUMNS_BY_TABLE[table_part]:
            return SqlValidationResult(
                valid=False,
                reason=f"Unknown or disallowed column: {table_part}.{column_part}.",
            )

    # For single-table queries, reject bare unknown column identifiers.
    if len(referenced_tables) == 1:
        table_name = next(iter(referenced_tables))
        allowed_cols = ALLOWED_COLUMNS_BY_TABLE[table_name]
        aliases: set[str] = set()
        for idx, token in enumerate(lower_tokens):
            if token == "as" and idx + 1 < len(lower_tokens):
                alias = lower_tokens[idx + 1]
                if IDENTIFIER_RE.match(alias):
                    aliases.add(alias)

        for token in lower_tokens:
            if not IDENTIFIER_RE.match(token):
                continue
            if token in sql_keywords or token == table_name or token in aliases:
                continue
            if token in allowed_cols or token == "*":
                continue
            # Likely an unknown column (e.g. SELECT password FROM invoices)
            return SqlValidationResult(
                valid=False,
                reason=f"Unknown or disallowed column: {token}.",
            )

    return SqlValidationResult(valid=True, reason=None, normalized_sql=normalize_sql(sql))
