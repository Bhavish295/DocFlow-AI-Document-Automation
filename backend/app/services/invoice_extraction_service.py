from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.models.document import Document, DocumentType
from app.models.invoice import Invoice
from app.schemas.invoice import InvoiceResponse
from app.services.invoice_extraction import (
    InvoiceExtractionResult,
    InvoiceExtractor,
    get_default_invoice_extractor,
)
from app.services.vendor_service import VendorService
from app.services.document_review import DocumentReviewService


class InvoiceExtractionService:
    def __init__(
        self,
        db: Session,
        extractor: InvoiceExtractor | None = None,
    ) -> None:
        self.db = db
        self.extractor = extractor or get_default_invoice_extractor()

    def extract_for_document(self, document_id: uuid.UUID) -> InvoiceResponse:
        document = self._get_or_404(document_id)
        self._validate_extractable(document)
        result = self.extractor.extract(document.extracted_text or "")
        invoice = self._upsert_invoice(document, result)
        self.db.flush()
        DocumentReviewService(self.db).evaluate_after_processing(document, invoice=invoice)
        self.db.commit()
        self.db.refresh(invoice)
        from app.services.workflow_engine import safe_dispatch_workflow_event

        safe_dispatch_workflow_event(
            self.db,
            trigger_event="invoice_extracted",
            entity_type="invoice",
            entity_id=invoice.id,
            metadata={"document_id": str(document.id), "source": "manual_extract"},
        )
        return InvoiceResponse.model_validate(invoice)

    def get_invoice(self, document_id: uuid.UUID) -> InvoiceResponse:
        document = self._get_or_404(document_id)
        invoice = self._get_invoice_for_document(document.id)
        if invoice is None:
            raise AppError("Invoice extraction is unavailable for this document.", status_code=404)
        return InvoiceResponse.model_validate(invoice)

    def extract_after_processing(self, document: Document) -> Invoice | None:
        if document.document_type != DocumentType.INVOICE.value:
            return None
        if not document.extracted_text:
            return None
        try:
            result = self.extractor.extract(document.extracted_text)
            return self._upsert_invoice(document, result)
        except Exception:
            return None

    def _validate_extractable(self, document: Document) -> None:
        if not document.extracted_text or not document.extracted_text.strip():
            raise AppError("Document has no extracted text to process.", status_code=400)
        if document.document_type != DocumentType.INVOICE.value:
            raise AppError("Invoice extraction is only available for invoice documents.", status_code=400)

    def _upsert_invoice(self, document: Document, result: InvoiceExtractionResult) -> Invoice:
        invoice = self._get_invoice_for_document(document.id)
        now = datetime.now(timezone.utc)

        if invoice is None:
            invoice = Invoice(document_id=document.id, created_at=now)
            self.db.add(invoice)

        invoice.vendor_name = result.vendor_name
        invoice.invoice_number = result.invoice_number
        invoice.invoice_date = result.invoice_date
        invoice.subtotal = self._to_numeric(result.subtotal)
        invoice.tax_amount = self._to_numeric(result.tax_amount)
        invoice.total_amount = self._to_numeric(result.total_amount)
        invoice.currency = result.currency
        invoice.extraction_confidence = result.extraction_confidence
        invoice.updated_at = now

        vendor = VendorService(self.db).find_or_create_vendor(result.vendor_name)
        invoice.vendor_id = vendor.id if vendor else None

        self.db.flush()
        return invoice

    def _get_invoice_for_document(self, document_id: uuid.UUID) -> Invoice | None:
        return self.db.scalar(select(Invoice).where(Invoice.document_id == document_id))

    def _get_or_404(self, document_id: uuid.UUID) -> Document:
        document = self.db.get(Document, document_id)
        if document is None:
            raise AppError("Document not found.", status_code=404)
        return document

    @staticmethod
    def _to_numeric(value: Decimal | None) -> Decimal | None:
        return value
