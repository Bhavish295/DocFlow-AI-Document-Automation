from __future__ import annotations

from collections.abc import Callable
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.models.document import Document, DocumentStatus, DocumentType
from app.models.document_processing_job import STAGE_PROGRESS, ProcessingJobStage
from app.models.document_review import ACTIVE_REVIEW_STATUSES, DocumentReview
from app.models.goods_receipt import GoodsReceipt
from app.models.invoice import Invoice
from app.models.purchase_order import PurchaseOrder
from app.schemas.document import DocumentResponse, DocumentTextResponse
from app.services.document_classification import DocumentClassificationService
from app.services.document_review import DocumentReviewService
from app.services.goods_receipt_extraction_service import GoodsReceiptExtractionService
from app.services.invoice_extraction_service import InvoiceExtractionService
from app.services.line_item_service import LineItemService, SUPPORTED_LINE_ITEM_TYPES
from app.services.purchase_order_extraction_service import PurchaseOrderExtractionService
from app.services.text_extraction import (
    PROCESSABLE_FILE_TYPES,
    TextExtractionError,
    extract_text_from_file,
)

StageCallback = Callable[[str, int], None]


class DocumentProcessingService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def process_document(
        self,
        document_id: uuid.UUID,
        *,
        on_stage: StageCallback | None = None,
    ) -> DocumentResponse:
        document = self._get_or_404(document_id)

        if document.file_type.lower() not in PROCESSABLE_FILE_TYPES:
            raise AppError(
                "Text extraction is only supported for PDF, PNG, JPG, and JPEG files.",
                status_code=400,
            )

        document.status = DocumentStatus.PROCESSING.value
        document.processing_error = None
        document.document_type = None
        document.classification_confidence = None
        self.db.commit()

        def report(stage: str) -> None:
            if on_stage is not None:
                on_stage(stage, STAGE_PROGRESS.get(stage, 0))

        try:
            report(ProcessingJobStage.TEXT_EXTRACTION.value)
            extracted = extract_text_from_file(Path(document.storage_path), document.file_type)
            if not extracted.strip():
                raise TextExtractionError("No readable text could be extracted from the document.")

            document.extracted_text = extracted
            document.processing_error = None
            document.status = DocumentStatus.PROCESSED.value
            document.processed_at = datetime.now(timezone.utc)

            report(ProcessingJobStage.CLASSIFICATION.value)
            DocumentClassificationService(self.db).apply_classification(document)

            report(ProcessingJobStage.STRUCTURED_EXTRACTION.value)
            warnings: list[str] = []
            invoice = None
            purchase_order = None
            goods_receipt = None
            if document.document_type == DocumentType.INVOICE.value:
                invoice = InvoiceExtractionService(self.db).extract_after_processing(document)
                if invoice is None:
                    warnings.append(
                        "Invoice classification succeeded but structured extraction failed."
                    )

            if document.document_type == DocumentType.PURCHASE_ORDER.value:
                purchase_order = PurchaseOrderExtractionService(self.db).extract_after_processing(
                    document
                )
                if purchase_order is None:
                    warnings.append(
                        "Purchase order classification succeeded but structured extraction failed."
                    )

            if document.document_type == DocumentType.GOODS_RECEIPT.value:
                goods_receipt = GoodsReceiptExtractionService(self.db).extract_after_processing(
                    document
                )
                if goods_receipt is None:
                    warnings.append(
                        "Goods receipt classification succeeded but structured extraction failed."
                    )

            report(ProcessingJobStage.LINE_ITEMS.value)
            if document.document_type in SUPPORTED_LINE_ITEM_TYPES:
                # Soft failure: never blocks header extraction/classification.
                LineItemService(self.db).extract_after_processing(document)

            if warnings:
                document.processing_error = " ".join(warnings)

            DocumentReviewService(self.db).evaluate_after_processing(
                document,
                invoice=invoice,
                purchase_order=purchase_order,
                goods_receipt=goods_receipt,
            )

            self.db.commit()
            self.db.refresh(document)

            from app.services.rag_indexing import RagIndexingService

            RagIndexingService(self.db).safe_index_document(document.id)
            self.db.refresh(document)

            from app.services.duplicate_detection import DuplicateDetectionService

            DuplicateDetectionService(self.db).safe_check_document(document.id)
            self.db.refresh(document)

            from app.services.workflow_engine import safe_dispatch_workflow_event

            safe_dispatch_workflow_event(
                self.db,
                trigger_event="document_processed",
                entity_type="document",
                entity_id=document.id,
                metadata={"document_type": document.document_type},
            )
            if invoice is not None:
                safe_dispatch_workflow_event(
                    self.db,
                    trigger_event="invoice_extracted",
                    entity_type="invoice",
                    entity_id=invoice.id,
                    metadata={"document_id": str(document.id)},
                )
            if purchase_order is not None:
                safe_dispatch_workflow_event(
                    self.db,
                    trigger_event="purchase_order_extracted",
                    entity_type="purchase_order",
                    entity_id=purchase_order.id,
                    metadata={"document_id": str(document.id)},
                )
            if goods_receipt is not None:
                safe_dispatch_workflow_event(
                    self.db,
                    trigger_event="goods_receipt_extracted",
                    entity_type="goods_receipt",
                    entity_id=goods_receipt.id,
                    metadata={"document_id": str(document.id)},
                )
            return self._to_response(document)
        except AppError:
            self.db.rollback()
            self.db.refresh(document)
            raise
        except Exception as exc:
            # Cooperative cancel from job runner — do not mark the document failed.
            if exc.__class__.__name__ == "JobCancelled":
                document = self._get_or_404(document_id)
                if document.status == DocumentStatus.PROCESSING.value:
                    document.status = (
                        DocumentStatus.PROCESSED.value
                        if document.extracted_text
                        else DocumentStatus.UPLOADED.value
                    )
                    self.db.commit()
                raise

            message = str(exc) if str(exc) else "Document processing failed."
            if isinstance(exc, TextExtractionError):
                message = str(exc)

            document = self._get_or_404(document_id)
            document.status = DocumentStatus.FAILED.value
            document.processing_error = message
            document.extracted_text = None
            document.document_type = None
            document.classification_confidence = None
            document.processed_at = datetime.now(timezone.utc)
            DocumentReviewService(self.db).create_processing_failed_review(document, message)
            self.db.commit()
            self.db.refresh(document)
            return self._to_response(document)

    def get_document_text(self, document_id: uuid.UUID) -> DocumentTextResponse:
        document = self._get_or_404(document_id)
        return DocumentTextResponse(
            id=document.id,
            original_filename=document.original_filename,
            status=document.status,
            extracted_text=document.extracted_text,
            processing_error=document.processing_error,
            processed_at=document.processed_at,
        )

    def _get_or_404(self, document_id: uuid.UUID) -> Document:
        document = self.db.get(Document, document_id)
        if document is None:
            raise AppError("Document not found.", status_code=404)
        return document

    def _to_response(self, document: Document) -> DocumentResponse:
        payload = DocumentResponse.model_validate(document)
        invoice = self.db.scalar(select(Invoice).where(Invoice.document_id == document.id))
        purchase_order = self.db.scalar(
            select(PurchaseOrder).where(PurchaseOrder.document_id == document.id)
        )
        goods_receipt = self.db.scalar(
            select(GoodsReceipt).where(GoodsReceipt.document_id == document.id)
        )
        active_review = self.db.scalar(
            select(DocumentReview.id).where(
                DocumentReview.document_id == document.id,
                DocumentReview.status.in_(ACTIVE_REVIEW_STATUSES),
            )
        )
        payload.has_invoice = invoice is not None
        payload.has_purchase_order = purchase_order is not None
        payload.has_goods_receipt = goods_receipt is not None
        payload.invoice_id = invoice.id if invoice else None
        payload.purchase_order_id = purchase_order.id if purchase_order else None
        payload.goods_receipt_id = goods_receipt.id if goods_receipt else None
        payload.requires_review = active_review is not None
        if invoice is not None:
            payload.vendor_id = invoice.vendor_id
            payload.vendor_name = invoice.vendor_name
        elif purchase_order is not None:
            payload.vendor_id = purchase_order.vendor_id
            payload.vendor_name = purchase_order.vendor_name
        elif goods_receipt is not None:
            payload.vendor_id = goods_receipt.vendor_id
            payload.vendor_name = goods_receipt.vendor_name
        return payload
