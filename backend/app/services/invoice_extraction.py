from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re
from typing import Protocol


AMOUNT_TOKEN = (
    r"(?P<currency>PKR|USD|EUR|Rs\.?|\$|€)?\s*"
    r"(?P<amount>\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)"
)

CURRENCY_MAP = {
    "pkr": "PKR",
    "rs": "PKR",
    "rs.": "PKR",
    "usd": "USD",
    "$": "USD",
    "eur": "EUR",
    "€": "EUR",
}

DATE_FORMATS = (
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%Y-%m-%d",
    "%d-%m-%y",
    "%d/%m/%y",
    "%m/%d/%Y",
    "%B %d, %Y",
    "%b %d, %Y",
    "%d %B %Y",
    "%d %b %Y",
)

FIELD_PATTERNS: dict[str, list[str]] = {
    "invoice_number": [
        r"(?:invoice\s*(?:number|no\.?|#)|inv\.?\s*no\.?)\s*[:#-]?\s*([A-Z0-9][A-Z0-9 sp/\-]{2,40})",
    ],
    "invoice_date": [
        r"(?:invoice\s*date|date\s*of\s*invoice|date)\s*[:#-]?\s*([0-9]{1,4}[-/][0-9]{1,2}[-/][0-9]{1,4}|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{2,4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4})",
    ],
    "subtotal": [
        r"(?:sub\s*-?\s*total|net\s*amount)\s*[:#-]?\s*" + AMOUNT_TOKEN,
    ],
    "tax_amount": [
        r"(?:sales\s*tax|vat|gst|tax(?:\s*amount)?)\s*[:#-]?\s*" + AMOUNT_TOKEN,
    ],
    "total_amount": [
        r"(?:grand\s*total|total\s*amount|amount\s*due)\s*[:#-]?\s*" + AMOUNT_TOKEN,
        r"(?m)^(?!.*\bsub\s*-?\s*total\b)\s*total\s*[:#-]?\s*" + AMOUNT_TOKEN,
    ],
}

SKIP_VENDOR_LINE = re.compile(
    r"^\s*(invoice|tax\s*invoice|page\s*\d+|bill\s*to|ship\s*to|date|invoice\s*no|"
    r"invoice\s*number|subtotal|total|tax|vat|gst|currency|"
    r"item\b|description\b|sku\b)\b",
    re.IGNORECASE,
)
TABLE_HEADER_LINE = re.compile(
    r"\|.*\b(qty|quantity|description|unit\s*price|amount|total)\b"
    r"|\b(item|sku|description)\b.+\b(qty|quantity)\b",
    re.IGNORECASE,
)
COMPANY_HINT = re.compile(
    r"\b(pvt\.?\s*ltd\.?|private\s+limited|ltd\.?|llc|inc\.?|corp\.?|company|co\.|gmbh|limited)\b",
    re.IGNORECASE,
)
EXPECTED_FIELDS = (
    "vendor_name",
    "invoice_number",
    "invoice_date",
    "subtotal",
    "tax_amount",
    "total_amount",
    "currency",
)


@dataclass
class InvoiceExtractionResult:
    vendor_name: str | None = None
    invoice_number: str | None = None
    invoice_date: date | None = None
    subtotal: Decimal | None = None
    tax_amount: Decimal | None = None
    total_amount: Decimal | None = None
    currency: str | None = None
    extraction_confidence: float = 0.0


class InvoiceExtractor(Protocol):
    def extract(self, text: str) -> InvoiceExtractionResult:
        """Extract structured invoice fields. Replaceable by an ML extractor later."""


def normalize_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[ \t]+", " ", normalized)
    return normalized.strip()


def parse_amount(raw: str) -> Decimal | None:
    cleaned = raw.strip().replace(",", "")
    try:
        value = Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None
    if value < 0:
        return None
    return value.quantize(Decimal("0.01"))


def normalize_currency(token: str | None) -> str | None:
    if not token:
        return None
    return CURRENCY_MAP.get(token.strip().lower(), token.strip().upper() or None)


def parse_date(raw: str) -> date | None:
    cleaned = re.sub(r"\s+", " ", raw.strip())
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def _search_labeled_value(text: str, patterns: list[str]) -> re.Match[str] | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match
    return None


def extract_currency_from_text(text: str) -> str | None:
    match = re.search(r"\b(PKR|USD|EUR)\b|(?:Rs\.?|\$|€)", text, flags=re.IGNORECASE)
    if not match:
        return None
    token = next((group for group in match.groups() if group), match.group(0))
    return normalize_currency(token)


def extract_vendor_name(text: str) -> str | None:
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    candidates: list[tuple[int, str]] = []

    for index, line in enumerate(lines[:12]):
        if SKIP_VENDOR_LINE.search(line):
            continue
        if TABLE_HEADER_LINE.search(line):
            continue
        if "|" in line and line.count("|") >= 2:
            continue
        if re.fullmatch(r"[\d\W]+", line):
            continue
        if len(line) < 3 or len(line) > 120:
            continue
        if re.search(r":\s*\d", line):
            continue

        score = 0
        if index < 3:
            score += 2
        if COMPANY_HINT.search(line):
            score += 4
        if line[:1].isupper():
            score += 1
        if not re.search(r"\d{3,}", line):
            score += 1
        candidates.append((score, line))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0], reverse=True)
    best_score, best_line = candidates[0]
    if best_score < 2:
        return None
    return best_line


def calculate_confidence(result: InvoiceExtractionResult) -> float:
    present = 0
    for field in EXPECTED_FIELDS:
        if getattr(result, field) is not None:
            present += 1
    ratio = present / len(EXPECTED_FIELDS)
    if ratio >= 0.85:
        return round(0.85 + (ratio - 0.85) * 1.0, 2)
    if ratio >= 0.5:
        return round(0.55 + (ratio - 0.5) * 0.6, 2)
    return round(max(0.15, ratio * 0.9), 2)


class RuleBasedInvoiceExtractor:
    def extract(self, text: str) -> InvoiceExtractionResult:
        normalized = normalize_text(text or "")
        result = InvoiceExtractionResult()
        if not normalized:
            result.extraction_confidence = 0.0
            return result

        compact = re.sub(r"\n+", "\n", normalized)

        number_match = _search_labeled_value(compact, FIELD_PATTERNS["invoice_number"])
        if number_match:
            result.invoice_number = number_match.group(1).strip(" :-#")

        date_match = _search_labeled_value(compact, FIELD_PATTERNS["invoice_date"])
        if date_match:
            result.invoice_date = parse_date(date_match.group(1))

        currencies_found: list[str] = []

        for field_name in ("subtotal", "tax_amount", "total_amount"):
            match = _search_labeled_value(compact, FIELD_PATTERNS[field_name])
            if not match:
                continue
            amount = parse_amount(match.group("amount"))
            setattr(result, field_name, amount)
            currency = normalize_currency(match.groupdict().get("currency"))
            if currency:
                currencies_found.append(currency)

        if currencies_found:
            result.currency = currencies_found[-1]
        else:
            result.currency = extract_currency_from_text(compact)

        currency_label = re.search(
            r"(?:currency)\s*[:#-]?\s*(PKR|USD|EUR|Rs\.?|\$|€)",
            compact,
            flags=re.IGNORECASE,
        )
        if currency_label:
            result.currency = normalize_currency(currency_label.group(1))

        result.vendor_name = extract_vendor_name(normalized)
        result.extraction_confidence = calculate_confidence(result)
        return result


def get_default_invoice_extractor() -> InvoiceExtractor:
    return RuleBasedInvoiceExtractor()
