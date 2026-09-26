"""Persist and retrieve document line items."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.models.document import Document, DocumentType
from app.models.document_line_item import DocumentLineItem
from app.schemas.line_item import DocumentLineItemListResponse, DocumentLineItemResponse
from app.services.line_item_extraction import (
    ExtractedLineItem,
    LineItemExtractor,
    get_default_line_item_extractor,
    quantity_type_for_document,
)


SUPPORTED_LINE_ITEM_TYPES = {
    DocumentType.INVOICE.value,
    DocumentType.PURCHASE_ORDER.value,
    DocumentType.GOODS_RECEIPT.value,
}


class LineItemService:
    def __init__(
        self,
        db: Session,
        extractor: LineItemExtractor | None = None,
    ) -> None:
        self.db = db
        self.extractor = extractor or get_default_line_item_extractor()

    def extract_for_document(self, document_id: uuid.UUID, *, commit: bool = True) -> DocumentLineItemListResponse:
        document = self._get_or_404(document_id)
        if document.document_type not in SUPPORTED_LINE_ITEM_TYPES:
            raise AppError(
                "Line-item extraction is only available for invoice, purchase order, "
                "and goods receipt documents.",
                status_code=400,
            )
        if not document.extracted_text or not document.extracted_text.strip():
            raise AppError("Document has no extracted text to process.", status_code=400)

        extracted = self.extractor.extract(
            document.extracted_text,
            document_type=document.document_type,
        )
        self.replace_line_items(document, extracted)
        if commit:
            self.db.commit()
        else:
            self.db.flush()
        return self.list_for_document(document_id)

    def extract_after_processing(self, document: Document) -> list[DocumentLineItem]:
        if document.document_type not in SUPPORTED_LINE_ITEM_TYPES:
            return []
        if not document.extracted_text:
            return []
        try:
            extracted = self.extractor.extract(
                document.extracted_text,
                document_type=document.document_type,
            )
            return self.replace_line_items(document, extracted)
        except Exception:
            return []

    def list_for_document(self, document_id: uuid.UUID) -> DocumentLineItemListResponse:
        document = self._get_or_404(document_id)
        rows = list(
            self.db.scalars(
                select(DocumentLineItem)
                .where(DocumentLineItem.document_id == document_id)
                .order_by(DocumentLineItem.line_number.asc())
            ).all()
        )
        return DocumentLineItemListResponse(
            document_id=document.id,
            document_type=document.document_type,
            items=[DocumentLineItemResponse.model_validate(row) for row in rows],
            total=len(rows),
        )

    def replace_line_items(
        self,
        document: Document,
        extracted: list[ExtractedLineItem],
    ) -> list[DocumentLineItem]:
        self.db.execute(
            delete(DocumentLineItem).where(DocumentLineItem.document_id == document.id)
        )
        now = datetime.now(timezone.utc)
        quantity_type = quantity_type_for_document(document.document_type or "")
        rows: list[DocumentLineItem] = []
        for item in extracted:
            row = DocumentLineItem(
                document_id=document.id,
                line_number=item.line_number,
                description=item.description,
                item_code=item.item_code,
                quantity=item.quantity,
                quantity_type=item.quantity_type or quantity_type,
                unit=item.unit,
                unit_price=item.unit_price,
                line_total=item.line_total,
                currency=item.currency,
                created_at=now,
                updated_at=now,
            )
            self.db.add(row)
            rows.append(row)
        self.db.flush()
        return rows

    def get_rows_for_document(self, document_id: uuid.UUID) -> list[DocumentLineItem]:
        return list(
            self.db.scalars(
                select(DocumentLineItem)
                .where(DocumentLineItem.document_id == document_id)
                .order_by(DocumentLineItem.line_number.asc())
            ).all()
        )

    def _get_or_404(self, document_id: uuid.UUID) -> Document:
        document = self.db.get(Document, document_id)
        if document is None:
            raise AppError("Document not found.", status_code=404)
        return document
