from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import re
from typing import Protocol

from app.services.invoice_extraction import (
    COMPANY_HINT,
    normalize_text,
    parse_date,
)


FIELD_PATTERNS: dict[str, list[str]] = {
    "grn_number": [
        r"(?:grn\s*(?:number|no\.?|#)|g\.?r\.?n\.?\s*(?:number|no\.?|#))\s*[:#-]?\s*"
        r"([A-Z0-9][A-Z0-9 /\-]{1,40})",
        r"(?:goods\s+receipt\s+(?:note\s+)?(?:number|no\.?|#)|receipt\s+no\.?)\s*[:#-]?\s*"
        r"([A-Z0-9][A-Z0-9 /\-]{1,40})",
    ],
    "grn_date": [
        r"(?:goods\s+receipt\s*date|grn\s*date|received\s*date|receipt\s*date|date\s*received|"
        r"date)\s*[:#-]?\s*"
        r"([0-9]{1,4}[-/][0-9]{1,2}[-/][0-9]{1,4}|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{2,4}|"
        r"\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4})",
    ],
    "po_number": [
        r"(?:purchase\s+order\s*(?:number|no\.?)|p\.?\s*o\.?\s*(?:number|no\.?|#)|"
        r"po\s*(?:number|no\.?|#))\s*[:#-]?\s*([A-Z0-9][A-Z0-9 /\-]{1,40})",
    ],
    "total_received_quantity": [
        r"(?:total\s+received\s+quantity|quantity\s+received|qty\s+received|"
        r"received\s+quantity|total\s+qty)\s*[:#-]?\s*([0-9]+(?:[.,][0-9]+)?)",
    ],
}

SKIP_VENDOR_LINE = re.compile(
    r"^\s*(goods\s+receipt|grn|g\.?r\.?n\.?|receipt\s+no|purchase\s+order|p\.?\s*o\.?|"
    r"po\s*number|page\s*\d+|ship\s*to|date|quantity|received|vendor|supplier)\b",
    re.IGNORECASE,
)

EXPECTED_FIELDS = (
    "grn_number",
    "grn_date",
    "vendor_name",
    "po_number",
    "total_received_quantity",
)


@dataclass
class GoodsReceiptExtractionResult:
    grn_number: str | None = None
    grn_date: date | None = None
    vendor_name: str | None = None
    po_number: str | None = None
    total_received_quantity: Decimal | None = None
    extraction_confidence: float = 0.0


class GoodsReceiptExtractor(Protocol):
    def extract(self, text: str) -> GoodsReceiptExtractionResult:
        """Extract structured GRN fields. Replaceable by an ML extractor later."""


def _search_labeled_value(text: str, patterns: list[str]) -> re.Match[str] | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match
    return None


def extract_vendor_name(text: str) -> str | None:
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    labeled = re.search(
        r"(?:supplier|vendor)\s*[:#-]?\s*([A-Za-z0-9][A-Za-z0-9 &.,'\-]{1,120})",
        text,
        flags=re.IGNORECASE,
    )
    if labeled:
        candidate = labeled.group(1).strip(" :-#")
        if candidate and not SKIP_VENDOR_LINE.search(candidate):
            return candidate

    candidates: list[tuple[int, str]] = []
    for index, line in enumerate(lines[:12]):
        if SKIP_VENDOR_LINE.search(line):
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


def calculate_confidence(result: GoodsReceiptExtractionResult) -> float:
    present = sum(1 for field in EXPECTED_FIELDS if getattr(result, field) is not None)
    ratio = present / len(EXPECTED_FIELDS)
    if ratio >= 0.85:
        return round(0.85 + (ratio - 0.85) * 1.0, 2)
    if ratio >= 0.5:
        return round(0.55 + (ratio - 0.5) * 0.6, 2)
    return round(max(0.15, ratio * 0.9), 2)


def parse_quantity(raw: str | None) -> Decimal | None:
    if not raw:
        return None
    cleaned = raw.strip().replace(",", "")
    try:
        value = Decimal(cleaned)
    except Exception:
        return None
    if value < 0:
        return None
    return value


class RuleBasedGoodsReceiptExtractor:
    def extract(self, text: str) -> GoodsReceiptExtractionResult:
        normalized = normalize_text(text or "")
        result = GoodsReceiptExtractionResult()
        if not normalized:
            result.extraction_confidence = 0.0
            return result

        compact = re.sub(r"\n+", "\n", normalized)

        grn_match = _search_labeled_value(compact, FIELD_PATTERNS["grn_number"])
        if grn_match:
            candidate = grn_match.group(1).strip(" :-#")
            if len(candidate) >= 3 and not re.fullmatch(r"TE|NOTE|NO", candidate, flags=re.IGNORECASE):
                result.grn_number = candidate

        date_match = _search_labeled_value(compact, FIELD_PATTERNS["grn_date"])
        if date_match:
            result.grn_date = parse_date(date_match.group(1))

        po_match = _search_labeled_value(compact, FIELD_PATTERNS["po_number"])
        if po_match:
            result.po_number = po_match.group(1).strip(" :-#")

        qty_match = _search_labeled_value(compact, FIELD_PATTERNS["total_received_quantity"])
        if qty_match:
            result.total_received_quantity = parse_quantity(qty_match.group(1))

        result.vendor_name = extract_vendor_name(normalized)
        result.extraction_confidence = calculate_confidence(result)
        return result


def get_default_goods_receipt_extractor() -> GoodsReceiptExtractor:
    return RuleBasedGoodsReceiptExtractor()
