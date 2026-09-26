from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.models.document import Document, DocumentType
from app.models.purchase_order import PurchaseOrder
from app.schemas.purchase_order import PurchaseOrderResponse
from app.services.purchase_order_extraction import (
    PurchaseOrderExtractionResult,
    PurchaseOrderExtractor,
    get_default_purchase_order_extractor,
)
from app.services.vendor_service import VendorService
from app.services.document_review import DocumentReviewService


class PurchaseOrderExtractionService:
    def __init__(
        self,
        db: Session,
        extractor: PurchaseOrderExtractor | None = None,
    ) -> None:
        self.db = db
        self.extractor = extractor or get_default_purchase_order_extractor()

    def extract_for_document(self, document_id: uuid.UUID) -> PurchaseOrderResponse:
        document = self._get_or_404(document_id)
        self._validate_extractable(document)
        result = self.extractor.extract(document.extracted_text or "")
        purchase_order = self._upsert_purchase_order(document, result)
        self.db.flush()
        DocumentReviewService(self.db).evaluate_after_processing(
            document,
            purchase_order=purchase_order,
        )
        self.db.commit()
        self.db.refresh(purchase_order)
        from app.services.workflow_engine import safe_dispatch_workflow_event

        safe_dispatch_workflow_event(
            self.db,
            trigger_event="purchase_order_extracted",
            entity_type="purchase_order",
            entity_id=purchase_order.id,
            metadata={"document_id": str(document.id), "source": "manual_extract"},
        )
        return PurchaseOrderResponse.model_validate(purchase_order)

    def get_purchase_order(self, document_id: uuid.UUID) -> PurchaseOrderResponse:
        document = self._get_or_404(document_id)
        purchase_order = self._get_po_for_document(document.id)
        if purchase_order is None:
            raise AppError(
                "Purchase order extraction is unavailable for this document.",
                status_code=404,
            )
        return PurchaseOrderResponse.model_validate(purchase_order)

    def extract_after_processing(self, document: Document) -> PurchaseOrder | None:
        if document.document_type != DocumentType.PURCHASE_ORDER.value:
            return None
        if not document.extracted_text:
            return None
        try:
            result = self.extractor.extract(document.extracted_text)
            return self._upsert_purchase_order(document, result)
        except Exception:
            return None

    def _validate_extractable(self, document: Document) -> None:
        if not document.extracted_text or not document.extracted_text.strip():
            raise AppError("Document has no extracted text to process.", status_code=400)
        if document.document_type != DocumentType.PURCHASE_ORDER.value:
            raise AppError(
                "Purchase order extraction is only available for purchase order documents.",
                status_code=400,
            )

    def _upsert_purchase_order(
        self,
        document: Document,
        result: PurchaseOrderExtractionResult,
    ) -> PurchaseOrder:
        purchase_order = self._get_po_for_document(document.id)
        now = datetime.now(timezone.utc)

        if purchase_order is None:
            purchase_order = PurchaseOrder(document_id=document.id, created_at=now)
            self.db.add(purchase_order)

        purchase_order.po_number = result.po_number
        purchase_order.vendor_name = result.vendor_name
        purchase_order.po_date = result.po_date
        purchase_order.subtotal = self._to_numeric(result.subtotal)
        purchase_order.tax_amount = self._to_numeric(result.tax_amount)
        purchase_order.total_amount = self._to_numeric(result.total_amount)
        purchase_order.currency = result.currency
        purchase_order.extraction_confidence = result.extraction_confidence
        purchase_order.updated_at = now

        vendor = VendorService(self.db).find_or_create_vendor(result.vendor_name)
        purchase_order.vendor_id = vendor.id if vendor else None

        self.db.flush()
        return purchase_order

    def _get_po_for_document(self, document_id: uuid.UUID) -> PurchaseOrder | None:
        return self.db.scalar(select(PurchaseOrder).where(PurchaseOrder.document_id == document_id))

    def _get_or_404(self, document_id: uuid.UUID) -> Document:
        document = self.db.get(Document, document_id)
        if document is None:
            raise AppError("Document not found.", status_code=404)
        return document

    @staticmethod
    def _to_numeric(value: Decimal | None) -> Decimal | None:
        return value
