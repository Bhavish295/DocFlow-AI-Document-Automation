from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.models.document import Document, DocumentType
from app.models.goods_receipt import GoodsReceipt
from app.schemas.goods_receipt import GoodsReceiptResponse
from app.services.document_review import DocumentReviewService
from app.services.goods_receipt_extraction import (
    GoodsReceiptExtractionResult,
    GoodsReceiptExtractor,
    get_default_goods_receipt_extractor,
)
from app.services.vendor_service import VendorService


class GoodsReceiptExtractionService:
    def __init__(
        self,
        db: Session,
        extractor: GoodsReceiptExtractor | None = None,
    ) -> None:
        self.db = db
        self.extractor = extractor or get_default_goods_receipt_extractor()

    def extract_for_document(self, document_id: uuid.UUID) -> GoodsReceiptResponse:
        document = self._get_or_404(document_id)
        self._validate_extractable(document)
        result = self.extractor.extract(document.extracted_text or "")
        goods_receipt = self._upsert_goods_receipt(document, result)
        self.db.flush()
        DocumentReviewService(self.db).evaluate_after_processing(
            document,
            goods_receipt=goods_receipt,
        )
        self.db.commit()
        self.db.refresh(goods_receipt)
        from app.services.workflow_engine import safe_dispatch_workflow_event

        safe_dispatch_workflow_event(
            self.db,
            trigger_event="goods_receipt_extracted",
            entity_type="goods_receipt",
            entity_id=goods_receipt.id,
            metadata={"document_id": str(document.id), "source": "manual_extract"},
        )
        return GoodsReceiptResponse.model_validate(goods_receipt)

    def get_goods_receipt(self, document_id: uuid.UUID) -> GoodsReceiptResponse:
        document = self._get_or_404(document_id)
        goods_receipt = self._get_grn_for_document(document.id)
        if goods_receipt is None:
            raise AppError(
                "Goods receipt extraction is unavailable for this document.",
                status_code=404,
            )
        return GoodsReceiptResponse.model_validate(goods_receipt)

    def extract_after_processing(self, document: Document) -> GoodsReceipt | None:
        if document.document_type != DocumentType.GOODS_RECEIPT.value:
            return None
        if not document.extracted_text:
            return None
        try:
            result = self.extractor.extract(document.extracted_text)
            return self._upsert_goods_receipt(document, result)
        except Exception:
            return None

    def _validate_extractable(self, document: Document) -> None:
        if not document.extracted_text or not document.extracted_text.strip():
            raise AppError("Document has no extracted text to process.", status_code=400)
        if document.document_type != DocumentType.GOODS_RECEIPT.value:
            raise AppError(
                "Goods receipt extraction is only available for goods receipt documents.",
                status_code=400,
            )

    def _upsert_goods_receipt(
        self,
        document: Document,
        result: GoodsReceiptExtractionResult,
    ) -> GoodsReceipt:
        goods_receipt = self._get_grn_for_document(document.id)
        now = datetime.now(timezone.utc)

        if goods_receipt is None:
            goods_receipt = GoodsReceipt(document_id=document.id, created_at=now)
            self.db.add(goods_receipt)

        goods_receipt.grn_number = result.grn_number
        goods_receipt.grn_date = result.grn_date
        goods_receipt.vendor_name = result.vendor_name
        goods_receipt.po_number = result.po_number
        goods_receipt.total_received_quantity = self._to_numeric(result.total_received_quantity)
        goods_receipt.extraction_confidence = result.extraction_confidence
        goods_receipt.updated_at = now

        vendor = VendorService(self.db).find_or_create_vendor(result.vendor_name)
        goods_receipt.vendor_id = vendor.id if vendor else None

        self.db.flush()
        return goods_receipt

    def _get_grn_for_document(self, document_id: uuid.UUID) -> GoodsReceipt | None:
        return self.db.scalar(select(GoodsReceipt).where(GoodsReceipt.document_id == document_id))

    def _get_or_404(self, document_id: uuid.UUID) -> Document:
        document = self.db.get(Document, document_id)
        if document is None:
            raise AppError("Document not found.", status_code=404)
        return document

    @staticmethod
    def _to_numeric(value: Decimal | None) -> Decimal | None:
        return value
