"""Deterministic line-item extraction from normalized document text."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re
from typing import Protocol

from app.models.document import DocumentType
from app.models.document_line_item import LineItemQuantityType
from app.services.invoice_extraction import normalize_currency, parse_amount


HEADER_HINT = re.compile(
    r"\b(item|sku|code|description|qty|quantity|unit\s*price|amount|total)\b",
    re.IGNORECASE,
)
SKIP_LINE = re.compile(
    r"^\s*(sub\s*-?\s*total|subtotal|tax|vat|gst|grand\s*total|invoice\s*total|"
    r"total\s*amount|amount\s*due|balance\s*due|balance|net\s*amount|"
    r"payment\s*terms|bill\s*to|ship\s*to|vendor|supplier|currency|"
    r"due\s*date|invoice\s*number|po\s*number|grn\s*number|page\s*\d+|"
    r"quantity\s+received|total\s+received|received\s+quantity|total\s+qty|"
    r"received\s*date|invoice\s*date|po\s*date|order\s*date|delivery\s*date|"
    r"total)\b",
    re.IGNORECASE,
)
SEPARATOR_ONLY = re.compile(r"^[\s|_\-=.]+$")
# Codes like SKU-1, SKU-A, ABC123 — letter present plus digit and/or separator.
SKU_TOKEN = re.compile(
    r"^(?=[A-Z0-9\-_/]*[A-Z])(?=.*[\d\-_\/])[A-Z0-9][A-Z0-9\-_/]{0,31}$",
    re.IGNORECASE,
)
UNIT_TOKEN = re.compile(
    r"^(pcs|pc|ea|each|unit|units|box|boxes|kg|g|lb|oz|hr|hrs|hour|hours|day|days|"
    r"set|sets|pack|packs)$",
    re.IGNORECASE,
)
NUMBER_TOKEN = re.compile(
    r"^(?P<currency>PKR|USD|EUR|GBP|Rs\.?|\$|€|£)?\s*"
    r"(?P<amount>-?\d{1,3}(?:,\d{3})*(?:\.\d+)?|-?\d+(?:\.\d+)?)\s*"
    r"(?P<currency2>PKR|USD|EUR|GBP|Rs\.?|\$|€|£)?$",
    re.IGNORECASE,
)


@dataclass
class ExtractedLineItem:
    line_number: int
    description: str | None = None
    item_code: str | None = None
    quantity: Decimal | None = None
    quantity_type: str | None = None
    unit: str | None = None
    unit_price: Decimal | None = None
    line_total: Decimal | None = None
    currency: str | None = None


class LineItemExtractor(Protocol):
    def extract(self, text: str, *, document_type: str) -> list[ExtractedLineItem]:
        """Extract line items from document text."""


def quantity_type_for_document(document_type: str) -> str | None:
    mapping = {
        DocumentType.INVOICE.value: LineItemQuantityType.INVOICED.value,
        DocumentType.PURCHASE_ORDER.value: LineItemQuantityType.ORDERED.value,
        DocumentType.GOODS_RECEIPT.value: LineItemQuantityType.RECEIVED.value,
    }
    return mapping.get(document_type)


def _split_cells(line: str) -> list[str]:
    if "|" in line:
        parts = [part.strip() for part in line.split("|")]
    elif "\t" in line:
        parts = [part.strip() for part in line.split("\t")]
    else:
        parts = [part.strip() for part in re.split(r"\s{2,}", line)]
        if len(parts) < 2:
            parts = line.split()
    return [part for part in parts if part]


def _parse_number(token: str) -> tuple[Decimal | None, str | None]:
    match = NUMBER_TOKEN.fullmatch(token.strip())
    if not match:
        return None, None
    raw = match.group("amount")
    try:
        value = Decimal(raw.replace(",", ""))
    except (InvalidOperation, AttributeError):
        return None, None
    currency = normalize_currency(match.group("currency") or match.group("currency2"))
    return value, currency


def _is_header(line: str, cells: list[str]) -> bool:
    joined = " ".join(cells).lower()
    if HEADER_HINT.search(joined) and not any(_parse_number(cell)[0] is not None for cell in cells):
        return True
    if re.search(r"\bqty\b|\bquantity\b", joined) and re.search(r"\b(item|description|sku)\b", joined):
        return True
    return False


def _looks_like_item_row(cells: list[str]) -> bool:
    if len(cells) < 2:
        return False
    numeric_count = sum(1 for cell in cells if _parse_number(cell)[0] is not None)
    return numeric_count >= 1


def _build_item(cells: list[str], line_number: int, quantity_type: str | None) -> ExtractedLineItem | None:
    numbers: list[tuple[int, Decimal, str | None]] = []
    units: list[str] = []
    text_parts: list[str] = []
    item_code: str | None = None

    for index, cell in enumerate(cells):
        amount, currency = _parse_number(cell)
        if amount is not None:
            numbers.append((index, amount, currency))
            continue
        if UNIT_TOKEN.fullmatch(cell):
            units.append(cell)
            continue
        if item_code is None and SKU_TOKEN.fullmatch(cell) and not cell.isdigit():
            item_code = cell.strip()
            continue
        text_parts.append(cell)

    if not numbers:
        return None

    description = " ".join(text_parts).strip() or None
    if description and SKIP_LINE.search(description):
        return None

    # Prefer first numeric as quantity when row also has prices, else sole numeric is quantity.
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    line_total: Decimal | None = None
    currency: str | None = None

    if len(numbers) == 1:
        quantity = numbers[0][1]
        currency = numbers[0][2]
    elif len(numbers) == 2:
        quantity = numbers[0][1]
        line_total = numbers[1][1]
        currency = numbers[1][2] or numbers[0][2]
    else:
        quantity = numbers[0][1]
        unit_price = numbers[1][1]
        line_total = numbers[-1][1]
        currency = numbers[-1][2] or numbers[1][2] or numbers[0][2]

    # Negative quantities are invalid — do not invent a substitute; drop the row.
    if quantity is not None and quantity < 0:
        return None
    if unit_price is not None and unit_price < 0:
        unit_price = None
    if line_total is not None and line_total < 0:
        line_total = None

    if description is None and item_code is None and quantity is None:
        return None

    return ExtractedLineItem(
        line_number=line_number,
        description=description,
        item_code=item_code,
        quantity=quantity,
        quantity_type=quantity_type,
        unit=units[0] if units else None,
        unit_price=unit_price,
        line_total=line_total,
        currency=currency,
    )


class RuleBasedLineItemExtractor:
    def extract(self, text: str, *, document_type: str) -> list[ExtractedLineItem]:
        if document_type not in {
            DocumentType.INVOICE.value,
            DocumentType.PURCHASE_ORDER.value,
            DocumentType.GOODS_RECEIPT.value,
        }:
            return []

        quantity_type = quantity_type_for_document(document_type)
        lines = [line.strip() for line in (text or "").replace("\r\n", "\n").split("\n")]
        items: list[ExtractedLineItem] = []
        line_number = 0

        for raw in lines:
            if not raw or SEPARATOR_ONLY.match(raw):
                continue
            if SKIP_LINE.search(raw):
                continue
            cells = _split_cells(raw)
            if not cells:
                continue
            if _is_header(raw, cells):
                continue
            if not _looks_like_item_row(cells):
                continue
            line_number += 1
            item = _build_item(cells, line_number, quantity_type)
            if item is None:
                line_number -= 1
                continue
            items.append(item)

        return items


def get_default_line_item_extractor() -> LineItemExtractor:
    return RuleBasedLineItemExtractor()
