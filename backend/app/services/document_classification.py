from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.models.document import Document, DocumentStatus, DocumentType
from app.models.document_review import (
    ACTIVE_REVIEW_STATUSES,
    DocumentReview,
    ReviewPriority,
    ReviewReason,
)
from app.models.goods_receipt import GoodsReceipt
from app.models.invoice import Invoice
from app.models.purchase_order import PurchaseOrder
from app.schemas.document import ClassificationResponse, DocumentResponse
from app.services.classification import DocumentClassifier, RuleBasedDocumentClassifier
from app.services.document_review import DocumentReviewService
from app.services.hybrid_classification import HybridClassificationResult, HybridDocumentClassifier
from app.services.ml_classification import (
    TrainResult,
    get_default_ml_classifier,
    load_starter_training_examples,
    reset_default_ml_classifier,
)


class DocumentClassificationService:
    def __init__(
        self,
        db: Session,
        classifier: DocumentClassifier | None = None,
        hybrid: HybridDocumentClassifier | None = None,
    ) -> None:
        self.db = db
        # `classifier` is preserved for tests that inject a custom rule-based classifier.
        rule = classifier or RuleBasedDocumentClassifier()
        self.hybrid = hybrid or HybridDocumentClassifier(rule_classifier=rule)

    def apply_classification(self, document: Document) -> HybridClassificationResult:
        result = self._safe_classify(document.extracted_text or "")
        document.document_type = result.document_type
        document.classification_confidence = result.confidence
        document.rule_based_document_type = result.rule_based_type
        document.rule_based_classification_confidence = result.rule_based_confidence
        document.ml_document_type = result.ml_type
        document.ml_classification_confidence = result.ml_confidence
        document.classification_method = result.classification_method
        if result.models_disagreed:
            DocumentReviewService(self.db).safe_create_review_if_needed(
                document_id=document.id,
                reason=ReviewReason.CLASSIFICATION_MODEL_DISAGREEMENT.value,
                priority=ReviewPriority.MEDIUM.value,
                details=(
                    "Rule-based and ML classifiers disagreed on the document type "
                    f"({result.rule_based_type} vs {result.ml_type})."
                ),
            )
        return result

    def classify_document(self, document_id: uuid.UUID) -> DocumentResponse:
        document = self._get_or_404(document_id)

        if document.status != DocumentStatus.PROCESSED.value or not document.extracted_text:
            raise AppError(
                "Document must be processed with extracted text before classification.",
                status_code=400,
            )

        self.apply_classification(document)
        DocumentReviewService(self.db).evaluate_after_processing(document)
        self.db.commit()
        self.db.refresh(document)
        return self._to_response(document)

    def get_classification(self, document_id: uuid.UUID) -> ClassificationResponse:
        document = self._get_or_404(document_id)

        if document.status != DocumentStatus.PROCESSED.value:
            raise AppError(
                "Document must be processed before classification results are available.",
                status_code=400,
            )

        return ClassificationResponse(
            document_id=document.id,
            document_type=document.document_type,
            confidence=document.classification_confidence,
            status=document.status,
            final_type=document.document_type,
            final_confidence=document.classification_confidence,
            rule_based_type=document.rule_based_document_type,
            rule_based_confidence=document.rule_based_classification_confidence,
            ml_type=document.ml_document_type,
            ml_confidence=document.ml_classification_confidence,
            classification_method=document.classification_method,
        )

    def train_model(self) -> TrainResult:
        examples = load_starter_training_examples()
        reset_default_ml_classifier()
        result = get_default_ml_classifier().train(examples)
        return result

    def get_model_status(self):
        return get_default_ml_classifier().get_status()

    def _safe_classify(self, text: str) -> HybridClassificationResult:
        try:
            return self.hybrid.classify_detailed(text)
        except Exception:
            return HybridClassificationResult(
                document_type=DocumentType.OTHER.value,
                confidence=0.2,
                classification_method="rule_based",
                rule_based_type=DocumentType.OTHER.value,
                rule_based_confidence=0.2,
                ml_type=None,
                ml_confidence=None,
                models_disagreed=False,
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
