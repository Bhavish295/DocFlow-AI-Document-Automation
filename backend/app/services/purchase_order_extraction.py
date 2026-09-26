from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import re
from typing import Protocol

from app.services.invoice_extraction import (
    AMOUNT_TOKEN,
    COMPANY_HINT,
    extract_currency_from_text,
    normalize_currency,
    normalize_text,
    parse_amount,
    parse_date,
)


FIELD_PATTERNS: dict[str, list[str]] = {
    "po_number": [
        r"(?:purchase\s+order\s*(?:number|no\.?)|p\.?\s*o\.?\s*(?:number|no\.?|#)|po\s*(?:number|no\.?|#))\s*[:#-]?\s*([A-Z0-9][A-Z0-9 /\-]{1,40})",
    ],
    "po_date": [
        r"(?:purchase\s+order\s*date|po\s*date|date)\s*[:#-]?\s*([0-9]{1,4}[-/][0-9]{1,2}[-/][0-9]{1,4}|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{2,4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4})",
    ],
    "subtotal": [
        r"(?:sub\s*-?\s*total|net\s*amount)\s*[:#-]?\s*" + AMOUNT_TOKEN,
    ],
    "tax_amount": [
        r"(?:sales\s*tax|vat|gst|tax(?:\s*amount)?)\s*[:#-]?\s*" + AMOUNT_TOKEN,
    ],
    "total_amount": [
        r"(?:grand\s*total|total\s*amount|amount\s*due)\s*[:#-]?\s*" + AMOUNT_TOKEN,
        r"(?m)^(?!.*\bsub\s*-?\s*total\b)\s*(?:total|amount)\s*[:#-]?\s*" + AMOUNT_TOKEN,
    ],
}

SKIP_VENDOR_LINE = re.compile(
    r"^\s*(purchase\s+order|p\.?\s*o\.?|po\s*number|po\s*no|page\s*\d+|bill\s*to|ship\s*to|"
    r"date|subtotal|total|tax|vat|gst|currency|quantity|unit\s*price)\b",
    re.IGNORECASE,
)

EXPECTED_FIELDS = (
    "vendor_name",
    "po_number",
    "po_date",
    "subtotal",
    "tax_amount",
    "total_amount",
    "currency",
)


@dataclass
class PurchaseOrderExtractionResult:
    vendor_name: str | None = None
    po_number: str | None = None
    po_date: date | None = None
    subtotal: Decimal | None = None
    tax_amount: Decimal | None = None
    total_amount: Decimal | None = None
    currency: str | None = None
    extraction_confidence: float = 0.0


class PurchaseOrderExtractor(Protocol):
    def extract(self, text: str) -> PurchaseOrderExtractionResult:
        """Extract structured PO fields. Replaceable by an ML extractor later."""


def _search_labeled_value(text: str, patterns: list[str]) -> re.Match[str] | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match
    return None


def extract_vendor_name(text: str) -> str | None:
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    candidates: list[tuple[int, str]] = []

    for index, line in enumerate(lines[:12]):
        if SKIP_VENDOR_LINE.search(line):
            continue
        if "|" in line and line.count("|") >= 2:
            continue
        if re.search(r"\b(item|sku|description)\b.+\b(qty|quantity)\b", line, re.IGNORECASE):
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


def calculate_confidence(result: PurchaseOrderExtractionResult) -> float:
    present = sum(1 for field in EXPECTED_FIELDS if getattr(result, field) is not None)
    ratio = present / len(EXPECTED_FIELDS)
    if ratio >= 0.85:
        return round(0.85 + (ratio - 0.85) * 1.0, 2)
    if ratio >= 0.5:
        return round(0.55 + (ratio - 0.5) * 0.6, 2)
    return round(max(0.15, ratio * 0.9), 2)


class RuleBasedPurchaseOrderExtractor:
    def extract(self, text: str) -> PurchaseOrderExtractionResult:
        normalized = normalize_text(text or "")
        result = PurchaseOrderExtractionResult()
        if not normalized:
            result.extraction_confidence = 0.0
            return result

        compact = re.sub(r"\n+", "\n", normalized)

        number_match = _search_labeled_value(compact, FIELD_PATTERNS["po_number"])
        if number_match:
            result.po_number = number_match.group(1).strip(" :-#")

        date_match = _search_labeled_value(compact, FIELD_PATTERNS["po_date"])
        if date_match:
            result.po_date = parse_date(date_match.group(1))

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


def get_default_purchase_order_extractor() -> PurchaseOrderExtractor:
    return RuleBasedPurchaseOrderExtractor()
