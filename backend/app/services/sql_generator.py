"""Provider-independent SQL generation for the read-only SQL agent."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

import httpx

from app.core.config import settings
from app.core.exceptions import AppError
from app.services.sql_schema import get_business_schema, schema_prompt_text


@dataclass(frozen=True)
class SqlGenerationResult:
    sql: str | None
    status: str  # ready | unsupported
    detail: str | None = None


class SQLGenerator(Protocol):
    def generate_sql(self, question: str, schema: dict[str, object] | None = None) -> SqlGenerationResult:
        """Generate a single read-only SELECT for the question."""


SQL_SYSTEM_RULES = """You are a read-only SQL generator for a business document platform.
Generate exactly one PostgreSQL-compatible SELECT statement.
Use ONLY the provided tables and columns.
Do not invent tables or columns.
Never modify data. Never use INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, CREATE, GRANT, REVOKE, or any write operation.
Never access secrets, credentials, environment variables, or system catalogs.
Return one SQL statement only.
Do not wrap SQL in markdown fences.
Do not include explanations in the SQL output.
Schema descriptions are authoritative.
"""


def _normalize_question(question: str) -> str:
    cleaned = (question or "").strip().lower()
    cleaned = cleaned.replace("?", " ")
    cleaned = re.sub(r"[^\w\s.]", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _extract_amount_threshold(question: str) -> float | None:
    match = re.search(
        r"(?:above|over|greater than|more than|>)\s*([0-9]+(?:[.,][0-9]+)?)",
        question.lower(),
    )
    if not match:
        return None
    raw = match.group(1).replace(",", "")
    try:
        return float(raw)
    except ValueError:
        return None


_KNOWN_CURRENCIES = frozenset(
    {
        "PKR",
        "USD",
        "EUR",
        "GBP",
        "INR",
        "AED",
        "SAR",
        "CAD",
        "AUD",
        "JPY",
        "CNY",
        "CHF",
    }
)


def _extract_currency_code(question: str) -> str | None:
    """Extract an optional ISO-like currency code from the question text."""
    text = question or ""
    labeled = re.search(
        r"\b(?:for|in|currency)\s+([A-Za-z]{3})\b",
        text,
        flags=re.IGNORECASE,
    )
    if labeled:
        code = labeled.group(1).upper()
        # Avoid false positives like "in the system" capturing "the".
        if code in _KNOWN_CURRENCIES:
            return code
    common = re.search(
        r"\b(" + "|".join(sorted(_KNOWN_CURRENCIES)) + r")\b",
        text,
        flags=re.IGNORECASE,
    )
    if common:
        return common.group(1).upper()
    return None


def _is_invoice_total_value_question(q: str) -> bool:
    """Detect natural-language questions asking for aggregate invoice monetary value."""
    if "total invoice amount" in q or "total invoice value" in q:
        return True
    if "sum of invoice" in q:
        return True
    if re.search(r"\b(total|sum)\b.*\b(amount|value|worth|totals?)\b.*\binvoices?\b", q):
        return True
    if re.search(r"\b(total|sum)\b.*\binvoices?\b.*\b(amount|value|worth|totals?)\b", q):
        return True
    if re.search(r"\b(total|sum)\b.*\binvoice\b.*\b(amount|value|worth|totals?)\b", q):
        return True
    if re.search(r"\binvoice\b.*\b(total|sum)\b.*\b(amount|value|worth|totals?)\b", q):
        return True
    if re.search(r"\bhow much\b.*\binvoices?\b.*\b(worth|total|value)\b", q):
        return True
    if re.search(r"\ball invoices?\b.*\b(worth|value|total)\b", q):
        return True
    if re.search(r"\binvoice totals?\b", q) and not _is_per_vendor_question(q):
        return True
    return False


def _is_per_vendor_question(q: str) -> bool:
    return bool(
        re.search(r"\b(by|per|for each|each|grouped by|group by|breakdown by)\s+vendors?\b", q)
        or re.search(r"\bvendor[- ]?wise\b", q)
    )


def _invoice_total_sql(*, currency: str | None = None) -> str:
    """Build a SELECT that never mixes currencies into one total."""
    if currency:
        safe = re.sub(r"[^A-Z]", "", currency.upper())[:3]
        if safe not in _KNOWN_CURRENCIES:
            safe = "XXX"
        return (
            "SELECT COALESCE(SUM(total_amount), 0) AS total_invoice_amount "
            "FROM invoices "
            f"WHERE currency = '{safe}'"
        )
    return (
        "SELECT COALESCE(currency, 'Unknown') AS currency, "
        "COALESCE(SUM(total_amount), 0) AS total_invoice_amount "
        "FROM invoices "
        "GROUP BY currency "
        "ORDER BY currency"
    )


class DeterministicSQLGenerator:
    """Development-friendly generator for common business analytics questions."""

    def generate_sql(self, question: str, schema: dict[str, object] | None = None) -> SqlGenerationResult:
        del schema  # Controlled schema is fixed in code for this provider.
        q = _normalize_question(question)
        if not q:
            return SqlGenerationResult(sql=None, status="unsupported", detail="Empty question.")

        threshold = _extract_amount_threshold(question)

        if re.search(r"\b(how many|count|number of)\b.*\binvoices?\b", q) or q in {
            "invoice count",
            "invoices",
        }:
            if threshold is not None:
                return SqlGenerationResult(
                    sql=(
                        "SELECT COUNT(*) AS invoice_count "
                        f"FROM invoices WHERE total_amount > {threshold}"
                    ),
                    status="ready",
                )
            return SqlGenerationResult(
                sql="SELECT COUNT(*) AS invoice_count FROM invoices",
                status="ready",
            )

        if re.search(r"\binvoices?\b.*\b(above|over|greater than|more than)\b", q) and threshold is not None:
            return SqlGenerationResult(
                sql=(
                    "SELECT COUNT(*) AS invoice_count "
                    f"FROM invoices WHERE total_amount > {threshold}"
                ),
                status="ready",
            )

        if re.search(
            r"\b(how many|count|number of)\b.*\b(purchase orders?|purchase_orders|pos?)\b",
            q,
        ) or "purchase order" in q and ("how many" in q or "count" in q or "exist" in q):
            return SqlGenerationResult(
                sql="SELECT COUNT(*) AS purchase_order_count FROM purchase_orders",
                status="ready",
            )

        if re.search(r"\b(how many|count|number of)\b.*\bvendors?\b", q) or q in {
            "vendor count",
            "vendors",
        }:
            return SqlGenerationResult(
                sql="SELECT COUNT(*) AS vendor_count FROM vendors",
                status="ready",
            )

        if re.search(r"\b(how many|count|number of)\b.*\bdocuments?\b", q) and "upload" not in q:
            return SqlGenerationResult(
                sql="SELECT COUNT(*) AS document_count FROM documents",
                status="ready",
            )

        if re.search(r"\b(validation )?mismatches?\b", q) or (
            "validation" in q and ("mismatch" in q or "mismatches" in q)
        ):
            return SqlGenerationResult(
                sql=(
                    "SELECT COUNT(*) AS mismatch_count FROM document_validations "
                    "WHERE status = 'mismatch'"
                ),
                status="ready",
            )

        # Must run before the generic total rule, or "total ... by vendor" loses its grouping.
        if _is_per_vendor_question(q) and "invoice" in q:
            # Per-vendor totals, kept separate per currency (never mix currencies).
            return SqlGenerationResult(
                sql=(
                    "SELECT COALESCE(vendor_name, 'Unknown') AS vendor_name, "
                    "COALESCE(currency, 'Unknown') AS currency, "
                    "COUNT(*) AS invoice_count, "
                    "COALESCE(SUM(total_amount), 0) AS invoice_total "
                    "FROM invoices GROUP BY vendor_name, currency "
                    "ORDER BY invoice_total DESC"
                ),
                status="ready",
            )

        if _is_invoice_total_value_question(q):
            currency = _extract_currency_code(question)
            return SqlGenerationResult(
                sql=_invoice_total_sql(currency=currency),
                status="ready",
            )

        if re.search(r"\bwhich vendors?\b.*\binvoices?\b", q) or (
            "vendors" in q and "have invoices" in q
        ):
            return SqlGenerationResult(
                sql=(
                    "SELECT DISTINCT COALESCE(v.name, i.vendor_name) AS vendor_name "
                    "FROM invoices i "
                    "LEFT JOIN vendors v ON v.id = i.vendor_id "
                    "WHERE COALESCE(v.name, i.vendor_name) IS NOT NULL "
                    "ORDER BY vendor_name"
                ),
                status="ready",
            )

        if re.search(r"\bdocuments?\b.*\buploaded\b.*\b(this month|current month)\b", q) or (
            "uploaded this month" in q
        ):
            month_start = datetime.now(timezone.utc).replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            )
            return SqlGenerationResult(
                sql=(
                    "SELECT COUNT(*) AS month_document_count FROM documents "
                    f"WHERE uploaded_at >= '{month_start.isoformat()}'"
                ),
                status="ready",
            )

        if re.search(r"\b(how many|count)\b.*\breviews?\b", q):
            return SqlGenerationResult(
                sql="SELECT COUNT(*) AS review_count FROM document_reviews",
                status="ready",
            )

        if re.search(r"\b(how many|count)\b.*\bchunks?\b", q):
            return SqlGenerationResult(
                sql="SELECT COUNT(*) AS chunk_count FROM document_chunks",
                status="ready",
            )

        return SqlGenerationResult(
            sql=None,
            status="unsupported",
            detail="I cannot answer this question using the available business data.",
        )


class LLMSQLGenerator:
    """Optional OpenAI-compatible SQL generator."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        api_base: str | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.LLM_API_KEY
        self.model = model or settings.LLM_MODEL or "gpt-4o-mini"
        self.api_base = (api_base or settings.LLM_API_BASE or "https://api.openai.com/v1").rstrip("/")

    def generate_sql(self, question: str, schema: dict[str, object] | None = None) -> SqlGenerationResult:
        if not self.api_key:
            raise AppError(
                "LLM_API_KEY is not configured for the selected SQL generator provider.",
                status_code=500,
            )
        schema = schema or get_business_schema()
        user_prompt = (
            f"{schema_prompt_text()}\n\n"
            f"Question:\n{question}\n\n"
            "Return only one SELECT statement."
        )
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SQL_SYSTEM_RULES},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            response = httpx.post(
                f"{self.api_base}/chat/completions",
                headers=headers,
                json=payload,
                timeout=60.0,
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            raise AppError("SQL generator provider request failed.", status_code=502) from exc

        sql = _clean_llm_sql(content)
        if not sql:
            return SqlGenerationResult(
                sql=None,
                status="unsupported",
                detail="I couldn't safely generate a query for that question.",
            )
        return SqlGenerationResult(sql=sql, status="ready")


def _clean_llm_sql(content: str) -> str | None:
    text = (content or "").strip()
    if not text:
        return None
    fence = re.search(r"```(?:sql)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    # Take first line-ish statement
    text = text.strip().rstrip(";")
    if not text:
        return None
    return text


class HybridSQLGenerator:
    """Prefer deterministic matches; optionally fall back to LLM generation."""

    def __init__(
        self,
        primary: SQLGenerator | None = None,
        fallback: SQLGenerator | None = None,
    ) -> None:
        self.primary = primary or DeterministicSQLGenerator()
        self.fallback = fallback

    def generate_sql(self, question: str, schema: dict[str, object] | None = None) -> SqlGenerationResult:
        result = self.primary.generate_sql(question, schema)
        if result.status == "ready" and result.sql:
            return result
        if self.fallback is None:
            return result
        return self.fallback.generate_sql(question, schema)


def get_default_sql_generator() -> SQLGenerator:
    provider = (settings.SQL_GENERATOR_PROVIDER or "deterministic").strip().lower()
    if provider in {"deterministic", "local", "default", "extractive"}:
        return DeterministicSQLGenerator()
    if provider in {"openai", "openai_compatible", "llm"}:
        return HybridSQLGenerator(
            primary=DeterministicSQLGenerator(),
            fallback=LLMSQLGenerator(),
        )
    raise AppError(
        f"Unsupported SQL_GENERATOR_PROVIDER '{settings.SQL_GENERATOR_PROVIDER}'.",
        status_code=500,
    )
