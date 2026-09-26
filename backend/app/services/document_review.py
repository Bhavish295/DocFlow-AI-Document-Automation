from __future__ import annotations

from datetime import datetime, timezone
from math import ceil
import uuid

from sqlalchemy import Select, asc, desc, func, select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.models.document import Document
from app.models.document_review import (
    ACTIVE_REVIEW_STATUSES,
    DocumentReview,
    ReviewPriority,
    ReviewReason,
    ReviewStatus,
)
from app.models.invoice import Invoice
from app.models.goods_receipt import GoodsReceipt
from app.models.purchase_order import PurchaseOrder
from app.models.validation import DocumentValidation
from app.schemas.document_review import (
    ReviewActionRequest,
    ReviewDetailResponse,
    ReviewDocumentSummary,
    ReviewInvoiceSummary,
    ReviewListResponse,
    ReviewPurchaseOrderSummary,
    ReviewResponse,
    ReviewUpdate,
    ReviewValidationSummary,
)


ALLOWED_STATUSES = {item.value for item in ReviewStatus}
ALLOWED_PRIORITIES = {item.value for item in ReviewPriority}
ALLOWED_REASONS = {item.value for item in ReviewReason}
ALLOWED_SORT_FIELDS = {
    "created_at": DocumentReview.created_at,
    "updated_at": DocumentReview.updated_at,
    "priority": DocumentReview.priority,
    "status": DocumentReview.status,
}
ALLOWED_SORT_ORDERS = {"asc", "desc"}
CLASSIFICATION_CONFIDENCE_THRESHOLD = 0.70
EXTRACTION_CONFIDENCE_THRESHOLD = 0.70


class DocumentReviewService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_active_review(self, document_id: uuid.UUID) -> DocumentReview | None:
        return self.db.scalar(
            select(DocumentReview)
            .where(
                DocumentReview.document_id == document_id,
                DocumentReview.status.in_(ACTIVE_REVIEW_STATUSES),
            )
            .order_by(DocumentReview.created_at.desc())
        )

    def create_review_if_needed(
        self,
        *,
        document_id: uuid.UUID,
        reason: str,
        details: str,
        priority: str = ReviewPriority.MEDIUM.value,
    ) -> DocumentReview | None:
        if reason not in ALLOWED_REASONS:
            raise AppError(f"Invalid review reason: {reason}", status_code=400)
        if priority not in ALLOWED_PRIORITIES:
            raise AppError(f"Invalid review priority: {priority}", status_code=400)

        existing = self.get_active_review(document_id)
        if existing is not None:
            return existing

        document = self.db.get(Document, document_id)
        if document is None:
            raise AppError("Document not found.", status_code=404)

        now = datetime.now(timezone.utc)
        review = DocumentReview(
            document_id=document_id,
            status=ReviewStatus.PENDING.value,
            priority=priority,
            reason=reason,
            details=details.strip(),
            created_at=now,
            updated_at=now,
        )
        self.db.add(review)
        self.db.flush()
        return review

    def safe_create_review_if_needed(
        self,
        *,
        document_id: uuid.UUID,
        reason: str,
        details: str,
        priority: str = ReviewPriority.MEDIUM.value,
    ) -> DocumentReview | None:
        try:
            with self.db.begin_nested():
                return self.create_review_if_needed(
                    document_id=document_id,
                    reason=reason,
                    details=details,
                    priority=priority,
                )
        except Exception:
            return None

    def list_reviews(
        self,
        *,
        status: str | None = None,
        priority: str | None = None,
        reason: str | None = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> ReviewListResponse:
        if page < 1:
            raise AppError("page must be >= 1.", status_code=400)
        if page_size < 1 or page_size > 100:
            raise AppError("page_size must be between 1 and 100.", status_code=400)

        filters = []
        if status:
            normalized = status.strip().lower()
            if normalized not in ALLOWED_STATUSES:
                raise AppError("Invalid status.", status_code=400)
            filters.append(DocumentReview.status == normalized)
        if priority:
            normalized = priority.strip().lower()
            if normalized not in ALLOWED_PRIORITIES:
                raise AppError("Invalid priority.", status_code=400)
            filters.append(DocumentReview.priority == normalized)
        if reason:
            normalized = reason.strip().lower()
            if normalized not in ALLOWED_REASONS:
                raise AppError("Invalid reason.", status_code=400)
            filters.append(DocumentReview.reason == normalized)

        sort_column, normalized_order = self._validate_sort(sort_by, sort_order)
        count_stmt = select(func.count()).select_from(DocumentReview)
        if filters:
            count_stmt = count_stmt.where(*filters)
        total = self.db.scalar(count_stmt) or 0

        query: Select[tuple[DocumentReview]] = select(DocumentReview)
        if filters:
            query = query.where(*filters)
        order_expr = asc(sort_column) if normalized_order == "asc" else desc(sort_column)
        reviews = self.db.scalars(
            query.order_by(order_expr, desc(DocumentReview.id))
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()

        document_ids = [review.document_id for review in reviews]
        documents = {
            document.id: document
            for document in (
                self.db.scalars(select(Document).where(Document.id.in_(document_ids))).all()
                if document_ids
                else []
            )
        }

        total_pages = ceil(total / page_size) if total else 0
        return ReviewListResponse(
            items=[self._to_list_item(review, documents.get(review.document_id)) for review in reviews],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1 and total > 0,
        )

    def get_review(self, review_id: uuid.UUID) -> ReviewDetailResponse:
        review = self._get_or_404(review_id)
        return self._to_detail(review)

    def update_review(self, review_id: uuid.UUID, payload: ReviewUpdate) -> ReviewDetailResponse:
        review = self._get_or_404(review_id)
        data = payload.model_dump(exclude_unset=True)

        if "status" in data and data["status"] is not None:
            status = data["status"].strip().lower()
            if status not in ALLOWED_STATUSES:
                raise AppError("Invalid status.", status_code=400)
            review.status = status
            if status in {ReviewStatus.APPROVED.value, ReviewStatus.REJECTED.value}:
                review.resolved_at = datetime.now(timezone.utc)
            elif status in ACTIVE_REVIEW_STATUSES:
                review.resolved_at = None

        if "priority" in data and data["priority"] is not None:
            priority = data["priority"].strip().lower()
            if priority not in ALLOWED_PRIORITIES:
                raise AppError("Invalid priority.", status_code=400)
            review.priority = priority

        if "reviewer_notes" in data:
            notes = data["reviewer_notes"]
            review.reviewer_notes = notes.strip() if isinstance(notes, str) and notes.strip() else notes

        review.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(review)
        return self._to_detail(review)

    def start_review(
        self,
        review_id: uuid.UUID,
        payload: ReviewActionRequest | None = None,
    ) -> ReviewDetailResponse:
        review = self._get_or_404(review_id)
        if payload and payload.reviewer_notes is not None:
            review.reviewer_notes = payload.reviewer_notes.strip() or None
        review.status = ReviewStatus.IN_REVIEW.value
        review.resolved_at = None
        review.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(review)
        return self._to_detail(review)

    def approve_review(
        self,
        review_id: uuid.UUID,
        payload: ReviewActionRequest | None = None,
    ) -> ReviewDetailResponse:
        return self._resolve(review_id, ReviewStatus.APPROVED.value, payload)

    def reject_review(
        self,
        review_id: uuid.UUID,
        payload: ReviewActionRequest | None = None,
    ) -> ReviewDetailResponse:
        return self._resolve(review_id, ReviewStatus.REJECTED.value, payload)

    def evaluate_after_processing(
        self,
        document: Document,
        invoice: Invoice | None = None,
        purchase_order: PurchaseOrder | None = None,
        goods_receipt: GoodsReceipt | None = None,
    ) -> None:
        if document.document_type == "other":
            self.safe_create_review_if_needed(
                document_id=document.id,
                reason=ReviewReason.UNKNOWN_DOCUMENT_TYPE.value,
                priority=ReviewPriority.MEDIUM.value,
                details="The document could not be confidently classified and requires manual review.",
            )

        confidence = document.classification_confidence
        if confidence is not None and confidence < CLASSIFICATION_CONFIDENCE_THRESHOLD:
            self.safe_create_review_if_needed(
                document_id=document.id,
                reason=ReviewReason.LOW_CLASSIFICATION_CONFIDENCE.value,
                priority=ReviewPriority.MEDIUM.value,
                details=(
                    f"Classification confidence is {confidence:.2f}, which is below the "
                    f"{CLASSIFICATION_CONFIDENCE_THRESHOLD:.2f} threshold."
                ),
            )

        if invoice is not None:
            self._evaluate_invoice(document, invoice)

        if purchase_order is not None:
            self._evaluate_purchase_order(document, purchase_order)

        if goods_receipt is not None:
            self._evaluate_goods_receipt(document, goods_receipt)

        self._apply_field_intelligence_review(
            document,
            invoice,
            purchase_order,
            goods_receipt,
        )

    def create_processing_failed_review(self, document: Document, error_message: str) -> None:
        details = (
            "Document processing failed and manual review is required."
            + (f" Error: {error_message}" if error_message else "")
        )
        self.safe_create_review_if_needed(
            document_id=document.id,
            reason=ReviewReason.PROCESSING_FAILED.value,
            priority=ReviewPriority.HIGH.value,
            details=details,
        )

    def create_validation_mismatch_review(
        self,
        *,
        document_id: uuid.UUID,
        mismatch_summary: str | None,
    ) -> None:
        details = mismatch_summary or "Invoice and purchase order fields do not match."
        self.safe_create_review_if_needed(
            document_id=document_id,
            reason=ReviewReason.VALIDATION_MISMATCH.value,
            priority=ReviewPriority.HIGH.value,
            details=details,
        )

    def _apply_field_intelligence_review(
        self,
        document: Document,
        invoice: Invoice | None,
        purchase_order: PurchaseOrder | None,
        goods_receipt: GoodsReceipt | None = None,
    ) -> None:
        from app.services.field_intelligence import (
            evaluate_goods_receipt_model,
            evaluate_invoice_model,
            evaluate_purchase_order_model,
            review_request_for_result,
        )

        if invoice is not None:
            request = review_request_for_result(evaluate_invoice_model(invoice))
            if request is not None:
                reason, priority, details = request
                self.safe_create_review_if_needed(
                    document_id=document.id,
                    reason=reason,
                    priority=priority,
                    details=details,
                )

        if purchase_order is not None:
            request = review_request_for_result(evaluate_purchase_order_model(purchase_order))
            if request is not None:
                reason, priority, details = request
                self.safe_create_review_if_needed(
                    document_id=document.id,
                    reason=reason,
                    priority=priority,
                    details=details,
                )

        if goods_receipt is not None:
            request = review_request_for_result(evaluate_goods_receipt_model(goods_receipt))
            if request is not None:
                reason, priority, details = request
                self.safe_create_review_if_needed(
                    document_id=document.id,
                    reason=reason,
                    priority=priority,
                    details=details,
                )

    def _evaluate_invoice(self, document: Document, invoice: Invoice) -> None:
        missing: list[str] = []
        if not invoice.invoice_number:
            missing.append("invoice_number")
        if invoice.invoice_date is None:
            missing.append("invoice_date")
        if not invoice.vendor_name:
            missing.append("vendor_name")
        if invoice.total_amount is None:
            missing.append("total")

        if missing:
            self.safe_create_review_if_needed(
                document_id=document.id,
                reason=ReviewReason.MISSING_REQUIRED_FIELDS.value,
                priority=ReviewPriority.MEDIUM.value,
                details="Missing required invoice fields: " + ", ".join(missing) + ".",
            )

        confidence = invoice.extraction_confidence
        if confidence is not None and confidence < EXTRACTION_CONFIDENCE_THRESHOLD:
            self.safe_create_review_if_needed(
                document_id=document.id,
                reason=ReviewReason.LOW_EXTRACTION_CONFIDENCE.value,
                priority=ReviewPriority.MEDIUM.value,
                details=(
                    f"Invoice extraction confidence is {confidence:.2f}, which is below the "
                    f"{EXTRACTION_CONFIDENCE_THRESHOLD:.2f} threshold."
                ),
            )

    def _evaluate_purchase_order(self, document: Document, purchase_order: PurchaseOrder) -> None:
        missing: list[str] = []
        if not purchase_order.po_number:
            missing.append("po_number")
        if not purchase_order.vendor_name:
            missing.append("vendor_name")
        if purchase_order.total_amount is None:
            missing.append("total")

        if missing:
            self.safe_create_review_if_needed(
                document_id=document.id,
                reason=ReviewReason.MISSING_REQUIRED_FIELDS.value,
                priority=ReviewPriority.MEDIUM.value,
                details="Missing required purchase order fields: " + ", ".join(missing) + ".",
            )

        confidence = purchase_order.extraction_confidence
        if confidence is not None and confidence < EXTRACTION_CONFIDENCE_THRESHOLD:
            self.safe_create_review_if_needed(
                document_id=document.id,
                reason=ReviewReason.LOW_EXTRACTION_CONFIDENCE.value,
                priority=ReviewPriority.MEDIUM.value,
                details=(
                    f"Purchase order extraction confidence is {confidence:.2f}, which is below the "
                    f"{EXTRACTION_CONFIDENCE_THRESHOLD:.2f} threshold."
                ),
            )

    def _evaluate_goods_receipt(self, document: Document, goods_receipt: GoodsReceipt) -> None:
        missing: list[str] = []
        if not goods_receipt.grn_number:
            missing.append("grn_number")
        if not goods_receipt.vendor_name:
            missing.append("vendor_name")
        if not goods_receipt.po_number:
            missing.append("po_number")

        if missing:
            self.safe_create_review_if_needed(
                document_id=document.id,
                reason=ReviewReason.MISSING_REQUIRED_FIELDS.value,
                priority=ReviewPriority.MEDIUM.value,
                details="Missing required goods receipt fields: " + ", ".join(missing) + ".",
            )

        confidence = goods_receipt.extraction_confidence
        if confidence is not None and confidence < EXTRACTION_CONFIDENCE_THRESHOLD:
            self.safe_create_review_if_needed(
                document_id=document.id,
                reason=ReviewReason.LOW_EXTRACTION_CONFIDENCE.value,
                priority=ReviewPriority.MEDIUM.value,
                details=(
                    f"Goods receipt extraction confidence is {confidence:.2f}, which is below the "
                    f"{EXTRACTION_CONFIDENCE_THRESHOLD:.2f} threshold."
                ),
            )

    def _resolve(
        self,
        review_id: uuid.UUID,
        status: str,
        payload: ReviewActionRequest | None,
    ) -> ReviewDetailResponse:
        review = self._get_or_404(review_id)
        if payload and payload.reviewer_notes is not None:
            review.reviewer_notes = payload.reviewer_notes.strip() or None
        now = datetime.now(timezone.utc)
        review.status = status
        review.resolved_at = now
        review.updated_at = now
        self.db.commit()
        self.db.refresh(review)
        from app.services.workflow_engine import safe_dispatch_workflow_event

        safe_dispatch_workflow_event(
            self.db,
            trigger_event="review_completed",
            entity_type="review",
            entity_id=review.id,
            metadata={"status": review.status, "document_id": str(review.document_id)},
        )
        return self._to_detail(review)

    def _get_or_404(self, review_id: uuid.UUID) -> DocumentReview:
        review = self.db.get(DocumentReview, review_id)
        if review is None:
            raise AppError("Review not found.", status_code=404)
        return review

    @staticmethod
    def _validate_sort(sort_by: str, sort_order: str):
        normalized_by = (sort_by or "created_at").strip().lower()
        normalized_order = (sort_order or "desc").strip().lower()
        if normalized_by not in ALLOWED_SORT_FIELDS:
            raise AppError("Invalid sort_by.", status_code=400)
        if normalized_order not in ALLOWED_SORT_ORDERS:
            raise AppError("Invalid sort_order.", status_code=400)
        return ALLOWED_SORT_FIELDS[normalized_by], normalized_order

    def _to_list_item(self, review: DocumentReview, document: Document | None) -> ReviewResponse:
        return ReviewResponse(
            id=review.id,
            document_id=review.document_id,
            status=review.status,
            priority=review.priority,
            reason=review.reason,
            details=review.details,
            reviewer_notes=review.reviewer_notes,
            created_at=review.created_at,
            updated_at=review.updated_at,
            resolved_at=review.resolved_at,
            document_filename=document.original_filename if document else None,
            document_type=document.document_type if document else None,
            document_status=document.status if document else None,
        )

    def _to_detail(self, review: DocumentReview) -> ReviewDetailResponse:
        document = self.db.get(Document, review.document_id)
        if document is None:
            raise AppError("Document not found for review.", status_code=404)

        invoice = self.db.scalar(select(Invoice).where(Invoice.document_id == document.id))
        purchase_order = self.db.scalar(
            select(PurchaseOrder).where(PurchaseOrder.document_id == document.id)
        )
        validation = None
        if invoice is not None:
            validation = self.db.scalar(
                select(DocumentValidation)
                .where(DocumentValidation.invoice_id == invoice.id)
                .order_by(DocumentValidation.created_at.desc())
            )

        return ReviewDetailResponse(
            id=review.id,
            document_id=review.document_id,
            status=review.status,
            priority=review.priority,
            reason=review.reason,
            details=review.details,
            reviewer_notes=review.reviewer_notes,
            created_at=review.created_at,
            updated_at=review.updated_at,
            resolved_at=review.resolved_at,
            document=ReviewDocumentSummary.model_validate(document),
            invoice=(
                ReviewInvoiceSummary(
                    id=invoice.id,
                    invoice_number=invoice.invoice_number,
                    invoice_date=invoice.invoice_date.isoformat() if invoice.invoice_date else None,
                    vendor_name=invoice.vendor_name,
                    subtotal=float(invoice.subtotal) if invoice.subtotal is not None else None,
                    tax_amount=float(invoice.tax_amount) if invoice.tax_amount is not None else None,
                    total_amount=float(invoice.total_amount) if invoice.total_amount is not None else None,
                    currency=invoice.currency,
                    extraction_confidence=invoice.extraction_confidence,
                )
                if invoice
                else None
            ),
            purchase_order=(
                ReviewPurchaseOrderSummary(
                    id=purchase_order.id,
                    po_number=purchase_order.po_number,
                    po_date=purchase_order.po_date.isoformat() if purchase_order.po_date else None,
                    vendor_name=purchase_order.vendor_name,
                    subtotal=float(purchase_order.subtotal) if purchase_order.subtotal is not None else None,
                    tax_amount=(
                        float(purchase_order.tax_amount) if purchase_order.tax_amount is not None else None
                    ),
                    total_amount=(
                        float(purchase_order.total_amount)
                        if purchase_order.total_amount is not None
                        else None
                    ),
                    currency=purchase_order.currency,
                    extraction_confidence=purchase_order.extraction_confidence,
                )
                if purchase_order
                else None
            ),
            validation=(
                ReviewValidationSummary(
                    id=validation.id,
                    status=validation.status,
                    vendor_match=validation.vendor_match,
                    currency_match=validation.currency_match,
                    subtotal_match=validation.subtotal_match,
                    tax_match=validation.tax_match,
                    total_match=validation.total_match,
                    mismatch_summary=validation.mismatch_summary,
                    invoice_number=validation.invoice_number,
                    po_number=validation.po_number,
                )
                if validation
                else None
            ),
        )
