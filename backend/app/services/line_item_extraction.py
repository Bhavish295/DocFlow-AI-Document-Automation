"""Deterministic line-item extraction from normalized document text."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
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
# Page markers inserted by text extraction, e.g. "--- Page 1 ---".
PAGE_MARKER = re.compile(r"^[\s\-=_*]*page\s*\d*[\s\-=_*]*$", re.IGNORECASE)
# "Label: value" metadata lines (not table rows). Tables use pipes/tabs/wide gaps.
KEY_VALUE_LINE = re.compile(r"^(?P<label>[A-Za-z][A-Za-z0-9 .#/()_\-]{0,40}?)\s*:\s*(?P<value>.*)$")
# Labels that describe a single item in "Key: Value" layouts.
KV_DESCRIPTION_LABELS = {"description", "item description", "item", "item name", "product", "service"}
KV_CODE_LABELS = {"item code", "sku", "code", "product code", "part number", "part no"}
KV_UNIT_LABELS = {"unit", "uom", "unit of measure"}
KV_UNIT_PRICE_LABELS = {"unit price", "rate", "price"}
KV_LINE_TOTAL_LABELS = {"line total", "amount", "line amount"}
KV_QUANTITY_LABELS = {
    "quantity": "generic",
    "qty": "generic",
    "ordered quantity": "ordered",
    "ordered qty": "ordered",
    "received quantity": "received",
    "received qty": "received",
    "quantity received": "received",
    "invoiced quantity": "invoiced",
    "invoiced qty": "invoiced",
    "billed quantity": "invoiced",
}
KV_ITEM_LABELS = (
    KV_DESCRIPTION_LABELS
    | KV_CODE_LABELS
    | KV_UNIT_LABELS
    | KV_UNIT_PRICE_LABELS
    | KV_LINE_TOTAL_LABELS
    | set(KV_QUANTITY_LABELS)
)
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


def _match_item_label_loose(line: str) -> tuple[str, str] | None:
    """Match an item label even when OCR dropped/mangled the colon ("Line Tota 450000").

    Short labels (qty, sku, unit, ...) must match exactly; longer ones may differ slightly.
    """
    words = line.split()
    # A table header such as "Item  Description  Qty  Price" is not a key/value line.
    if HEADER_HINT.search(" ".join(words[1:])) and not re.search(r"\d", line):
        return None
    best: tuple[float, str, str] | None = None
    for label in KV_ITEM_LABELS:
        size = len(label.split())
        if len(words) <= size:
            continue
        head = " ".join(words[:size]).lower().rstrip(":.;,")
        value = " ".join(words[size:]).lstrip(":.;, ").strip()
        if not value:
            continue
        if head == label:
            score = 1.0
        elif len(label) >= 5:
            score = SequenceMatcher(None, head, label).ratio()
            if score < 0.85:
                continue
        else:
            continue
        if best is None or score > best[0] or (score == best[0] and len(label) > len(best[1])):
            best = (score, label, value)
    return (best[1], best[2]) if best else None


def _parse_key_value(line: str) -> tuple[str, str] | None:
    if "|" in line or "\t" in line:
        return None
    match = KEY_VALUE_LINE.match(line)
    if match:
        label = re.sub(r"\s+", " ", match.group("label")).strip().lower()
        return label, match.group("value").strip()
    return _match_item_label_loose(line)


def _build_kv_item(
    fields: dict[str, str],
    line_number: int,
    quantity_type: str | None,
) -> ExtractedLineItem | None:
    """Build one item from a "Key: Value" block (e.g. Description / Item Code / Received Quantity)."""
    description = next((fields[k] for k in KV_DESCRIPTION_LABELS if fields.get(k)), None)
    item_code = next((fields[k] for k in KV_CODE_LABELS if fields.get(k)), None)
    unit = next((fields[k] for k in KV_UNIT_LABELS if fields.get(k)), None)

    def number(labels: set[str]) -> tuple[Decimal | None, str | None]:
        for label in labels:
            if fields.get(label):
                value, currency = _parse_number(fields[label])
                if value is not None:
                    return value, currency
        return None, None

    # Prefer the quantity that matches this document type, then any generic quantity.
    quantity: Decimal | None = None
    preferred = [label for label, kind in KV_QUANTITY_LABELS.items() if kind == quantity_type]
    generic = [label for label, kind in KV_QUANTITY_LABELS.items() if kind == "generic"]
    others = [label for label in KV_QUANTITY_LABELS if label not in preferred and label not in generic]
    for label in preferred + generic + others:
        if fields.get(label):
            value, _ = _parse_number(fields[label])
            if value is not None:
                quantity = value
                break

    unit_price, price_currency = number(KV_UNIT_PRICE_LABELS)
    line_total, total_currency = number(KV_LINE_TOTAL_LABELS)

    if description is None and item_code is None:
        return None
    if quantity is not None and quantity < 0:
        return None

    return ExtractedLineItem(
        line_number=line_number,
        description=description,
        item_code=item_code,
        quantity=quantity,
        quantity_type=quantity_type,
        unit=unit,
        unit_price=unit_price if unit_price is None or unit_price >= 0 else None,
        line_total=line_total if line_total is None or line_total >= 0 else None,
        currency=total_currency or price_currency,
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
        kv_fields: dict[str, str] = {}

        def flush_kv() -> None:
            nonlocal line_number
            if kv_fields:
                item = _build_kv_item(kv_fields, line_number + 1, quantity_type)
                if item is not None:
                    line_number += 1
                    items.append(item)
                kv_fields.clear()

        for raw in lines:
            if not raw or SEPARATOR_ONLY.match(raw) or PAGE_MARKER.match(raw):
                continue
            key_value = _parse_key_value(raw)
            if key_value is not None:
                label, value = key_value
                if label in KV_ITEM_LABELS:
                    # A repeated field means the next item's block has started.
                    if value and label in kv_fields:
                        flush_kv()
                    if value:
                        kv_fields[label] = value
                else:
                    # Any other "Label: value" line is document metadata, never a table row.
                    flush_kv()
                continue
            flush_kv()
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

        flush_kv()
        return items


def get_default_line_item_extractor() -> LineItemExtractor:
    return RuleBasedLineItemExtractor()
