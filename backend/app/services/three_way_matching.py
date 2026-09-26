"""Deterministic Invoice ↔ Purchase Order ↔ Goods Receipt matching."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.models.document import Document, DocumentType
from app.models.document_relationship import DocumentRelationship, DocumentRelationshipType
from app.models.document_review import ReviewPriority, ReviewReason
from app.models.goods_receipt import GoodsReceipt
from app.models.invoice import Invoice
from app.models.purchase_order import PurchaseOrder
from app.models.three_way_match import ThreeWayMatch
from app.models.validation import ValidationStatus
from app.schemas.three_way_match import (
    ThreeWayDimensionResult,
    ThreeWayDocumentSummary,
    ThreeWayMatchListResponse,
    ThreeWayMatchRequest,
    ThreeWayMatchResponse,
    ThreeWayQuantityEvidenceItem,
)
from app.services.document_relationship_service import (
    GRN_NUMBER_PATTERNS,
    PO_NUMBER_PATTERNS,
    extract_labeled_number,
    normalize_match_key,
)
from app.services.document_review import DocumentReviewService
from app.services.line_item_service import LineItemService
from app.services.quantity_matching import match_line_items, summarize_quantity_evidence
from app.services.validation_service import ValidationService


STATUS_MATCHED = ValidationStatus.MATCHED.value
STATUS_MISMATCH = ValidationStatus.MISMATCH.value
STATUS_NEEDS_REVIEW = ValidationStatus.NEEDS_REVIEW.value
STATUS_NOT_EVALUABLE = "not_evaluable"

REQUIRED_RELATIONSHIP_TYPES = (
    DocumentRelationshipType.INVOICE_PURCHASE_ORDER.value,
    DocumentRelationshipType.GOODS_RECEIPT_PURCHASE_ORDER.value,
    DocumentRelationshipType.INVOICE_GOODS_RECEIPT.value,
)


@dataclass
class DimensionOutcome:
    name: str
    status: str
    detail: str | None = None
    matched_entry: str | None = None
    mismatched_entry: str | None = None
    missing_entry: str | None = None


@dataclass
class MatchComputation:
    status: str
    overall_confidence: float
    vendor: DimensionOutcome
    po_reference: DimensionOutcome
    grn_reference: DimensionOutcome
    quantity: DimensionOutcome
    financial: DimensionOutcome
    relationships: DimensionOutcome
    matched_fields: list[str] = field(default_factory=list)
    mismatched_fields: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    quantity_evidence: list[dict] = field(default_factory=list)
    explanation: str = ""
    invoice_po_validation_id: uuid.UUID | None = None
    invoice_po_validation_status: str | None = None


class ThreeWayMatchingService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def run_match(self, payload: ThreeWayMatchRequest) -> ThreeWayMatchResponse:
        invoice_doc, po_doc, grn_doc, invoice, purchase_order, goods_receipt = (
            self._load_and_validate_documents(payload)
        )
        computation = self._compute(
            invoice_doc=invoice_doc,
            po_doc=po_doc,
            grn_doc=grn_doc,
            invoice=invoice,
            purchase_order=purchase_order,
            goods_receipt=goods_receipt,
        )
        row = self._upsert_result(payload, computation)
        self._maybe_create_review(invoice_doc, computation)
        self.db.commit()
        self.db.refresh(row)
        return self._to_response(
            row,
            invoice_doc=invoice_doc,
            po_doc=po_doc,
            grn_doc=grn_doc,
            invoice=invoice,
            purchase_order=purchase_order,
            goods_receipt=goods_receipt,
            invoice_po_validation_status=computation.invoice_po_validation_status,
        )

    def get_match(self, match_id: uuid.UUID) -> ThreeWayMatchResponse:
        row = self.db.get(ThreeWayMatch, match_id)
        if row is None:
            raise AppError("Three-way match not found.", status_code=404)
        return self._response_for_row(row)

    def list_matches(self, page: int = 1, page_size: int = 50) -> ThreeWayMatchListResponse:
        if page < 1:
            raise AppError("page must be >= 1.", status_code=400)
        if page_size < 1 or page_size > 100:
            raise AppError("page_size must be between 1 and 100.", status_code=400)

        total = self.db.scalar(select(func.count()).select_from(ThreeWayMatch)) or 0
        rows = self.db.scalars(
            select(ThreeWayMatch)
            .order_by(ThreeWayMatch.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        items = [self._response_for_row(row) for row in rows]
        return ThreeWayMatchListResponse(items=items, total=total, page=page, page_size=page_size)

    def _load_and_validate_documents(
        self,
        payload: ThreeWayMatchRequest,
    ) -> tuple[Document, Document, Document, Invoice, PurchaseOrder, GoodsReceipt]:
        ids = {
            payload.invoice_document_id,
            payload.purchase_order_document_id,
            payload.goods_receipt_document_id,
        }
        if len(ids) != 3:
            raise AppError(
                "Invoice, purchase order, and goods receipt must be three distinct documents.",
                status_code=400,
            )

        invoice_doc = self._get_document(payload.invoice_document_id, DocumentType.INVOICE.value)
        po_doc = self._get_document(
            payload.purchase_order_document_id, DocumentType.PURCHASE_ORDER.value
        )
        grn_doc = self._get_document(
            payload.goods_receipt_document_id, DocumentType.GOODS_RECEIPT.value
        )

        invoice = self.db.scalar(select(Invoice).where(Invoice.document_id == invoice_doc.id))
        purchase_order = self.db.scalar(
            select(PurchaseOrder).where(PurchaseOrder.document_id == po_doc.id)
        )
        goods_receipt = self.db.scalar(
            select(GoodsReceipt).where(GoodsReceipt.document_id == grn_doc.id)
        )
        if invoice is None:
            raise AppError("Invoice extraction data is missing for the invoice document.", status_code=400)
        if purchase_order is None:
            raise AppError(
                "Purchase order extraction data is missing for the purchase order document.",
                status_code=400,
            )
        if goods_receipt is None:
            raise AppError(
                "Goods receipt extraction data is missing for the goods receipt document.",
                status_code=400,
            )
        return invoice_doc, po_doc, grn_doc, invoice, purchase_order, goods_receipt

    def _get_document(self, document_id: uuid.UUID, expected_type: str) -> Document:
        document = self.db.get(Document, document_id)
        if document is None:
            raise AppError("Document not found.", status_code=404)
        if document.document_type != expected_type:
            raise AppError(
                f"Document {document_id} must be type '{expected_type}', "
                f"found '{document.document_type or 'unknown'}'.",
                status_code=400,
            )
        return document

    def _compute(
        self,
        *,
        invoice_doc: Document,
        po_doc: Document,
        grn_doc: Document,
        invoice: Invoice,
        purchase_order: PurchaseOrder,
        goods_receipt: GoodsReceipt,
    ) -> MatchComputation:
        vendor = self._compare_vendors(invoice, purchase_order, goods_receipt)
        po_reference = self._compare_po_references(invoice_doc, purchase_order, goods_receipt)
        grn_reference = self._compare_grn_references(invoice_doc, goods_receipt)
        quantity, quantity_evidence = self._quantity_dimension(
            invoice_doc_id=invoice_doc.id,
            po_doc_id=po_doc.id,
            grn_doc_id=grn_doc.id,
        )
        financial, validation_id, validation_status = self._financial_dimension(
            invoice, purchase_order
        )
        relationships = self._relationship_dimension(invoice_doc, po_doc, grn_doc)

        dimensions = [vendor, po_reference, grn_reference, quantity, financial, relationships]
        status = self._resolve_overall(dimensions)
        confidence = self._confidence(status, dimensions)

        matched = [item.matched_entry for item in dimensions if item.matched_entry]
        mismatched = [item.mismatched_entry for item in dimensions if item.mismatched_entry]
        missing = [item.missing_entry for item in dimensions if item.missing_entry]
        explanation = self._build_explanation(status, dimensions, quantity_evidence)

        return MatchComputation(
            status=status,
            overall_confidence=confidence,
            vendor=vendor,
            po_reference=po_reference,
            grn_reference=grn_reference,
            quantity=quantity,
            financial=financial,
            relationships=relationships,
            matched_fields=matched,
            mismatched_fields=mismatched,
            missing_fields=missing,
            quantity_evidence=quantity_evidence,
            explanation=explanation,
            invoice_po_validation_id=validation_id,
            invoice_po_validation_status=validation_status,
        )

    def _compare_vendors(
        self,
        invoice: Invoice,
        purchase_order: PurchaseOrder,
        goods_receipt: GoodsReceipt,
    ) -> DimensionOutcome:
        values = {
            "Invoice": invoice.vendor_name,
            "PO": purchase_order.vendor_name,
            "GRN": goods_receipt.vendor_name,
        }
        present = {label: name for label, name in values.items() if name and str(name).strip()}
        if len(present) < 3:
            missing_labels = [label for label, name in values.items() if label not in present]
            return DimensionOutcome(
                name="vendor",
                status=STATUS_NEEDS_REVIEW,
                detail="Vendor needs review: missing on " + ", ".join(missing_labels),
                missing_entry="Vendor: missing on " + ", ".join(missing_labels),
            )

        normalize = ValidationService._normalize_vendor
        normalized = {label: normalize(name) for label, name in present.items()}
        unique = set(normalized.values())
        if len(unique) == 1:
            display = present["Invoice"]
            return DimensionOutcome(
                name="vendor",
                status=STATUS_MATCHED,
                detail=f"Vendor matched across Invoice, PO, and GRN: {display}",
                matched_entry=f"Vendor: {display}",
            )

        parts = [f"{label}={present[label]}" for label in ("Invoice", "PO", "GRN")]
        return DimensionOutcome(
            name="vendor",
            status=STATUS_MISMATCH,
            detail="Vendor mismatch: " + "; ".join(parts),
            mismatched_entry="Vendor: " + "; ".join(parts),
        )

    def _compare_po_references(
        self,
        invoice_doc: Document,
        purchase_order: PurchaseOrder,
        goods_receipt: GoodsReceipt,
    ) -> DimensionOutcome:
        invoice_po = extract_labeled_number(invoice_doc.extracted_text, PO_NUMBER_PATTERNS)
        po_number = purchase_order.po_number
        grn_po = goods_receipt.po_number
        values = {
            "Invoice PO reference": invoice_po,
            "PO number": po_number,
            "GRN PO reference": grn_po,
        }
        present = {label: value for label, value in values.items() if value and str(value).strip()}
        if len(present) < 3:
            missing_labels = [label for label in values if label not in present]
            return DimensionOutcome(
                name="po_reference",
                status=STATUS_NEEDS_REVIEW,
                detail="PO reference needs review: missing " + ", ".join(missing_labels),
                missing_entry="PO reference: missing " + ", ".join(missing_labels),
            )

        keys = {label: normalize_match_key(value) for label, value in present.items()}
        if len(set(keys.values())) == 1:
            display = po_number or next(iter(present.values()))
            return DimensionOutcome(
                name="po_reference",
                status=STATUS_MATCHED,
                detail=f"PO reference matched: {display}",
                matched_entry=f"PO reference: {display}",
            )

        parts = [f"{label}={present[label]}" for label in values]
        return DimensionOutcome(
            name="po_reference",
            status=STATUS_MISMATCH,
            detail="PO reference mismatch: " + "; ".join(parts),
            mismatched_entry="PO reference: " + "; ".join(parts),
        )

    def _compare_grn_references(
        self,
        invoice_doc: Document,
        goods_receipt: GoodsReceipt,
    ) -> DimensionOutcome:
        invoice_grn = extract_labeled_number(invoice_doc.extracted_text, GRN_NUMBER_PATTERNS)
        grn_number = goods_receipt.grn_number
        if not invoice_grn:
            return DimensionOutcome(
                name="grn_reference",
                status=STATUS_NEEDS_REVIEW,
                detail=(
                    "GRN reference needs review: invoice has no GRN/receipt reference "
                    "(missing reference is not treated as a mismatch)."
                ),
                missing_entry="GRN reference: missing on invoice",
            )
        if not grn_number:
            return DimensionOutcome(
                name="grn_reference",
                status=STATUS_NEEDS_REVIEW,
                detail="GRN reference needs review: goods receipt has no GRN number.",
                missing_entry="GRN reference: missing on goods receipt",
            )
        if normalize_match_key(invoice_grn) == normalize_match_key(grn_number):
            return DimensionOutcome(
                name="grn_reference",
                status=STATUS_MATCHED,
                detail=f"GRN reference matched: {grn_number}",
                matched_entry=f"GRN reference: {grn_number}",
            )
        return DimensionOutcome(
            name="grn_reference",
            status=STATUS_MISMATCH,
            detail=f"GRN reference mismatch: Invoice={invoice_grn}; GRN={grn_number}",
            mismatched_entry=f"GRN reference: Invoice={invoice_grn}; GRN={grn_number}",
        )

    def _quantity_dimension(
        self,
        *,
        invoice_doc_id: uuid.UUID,
        po_doc_id: uuid.UUID,
        grn_doc_id: uuid.UUID,
    ) -> tuple[DimensionOutcome, list[dict]]:
        service = LineItemService(self.db)
        po_items = service.get_rows_for_document(po_doc_id)
        grn_items = service.get_rows_for_document(grn_doc_id)
        invoice_items = service.get_rows_for_document(invoice_doc_id)
        evidence_rows = match_line_items(po_items, grn_items, invoice_items)
        status, detail, payload, matched_entry, mismatched_entry, missing_entry = (
            summarize_quantity_evidence(evidence_rows)
        )
        return (
            DimensionOutcome(
                name="quantity",
                status=status,
                detail=detail,
                matched_entry=matched_entry,
                mismatched_entry=mismatched_entry,
                missing_entry=missing_entry,
            ),
            payload,
        )

    def _financial_dimension(
        self,
        invoice: Invoice,
        purchase_order: PurchaseOrder,
    ) -> tuple[DimensionOutcome, uuid.UUID | None, str | None]:
        validation = ValidationService(self.db).validate_invoice_against_po(
            invoice.id,
            purchase_order.id,
            commit=False,
            create_review=False,
        )
        status = validation.status
        if status == STATUS_MATCHED:
            outcome = DimensionOutcome(
                name="financial",
                status=STATUS_MATCHED,
                detail="Invoice ↔ PO financial validation matched.",
                matched_entry="Invoice financial validation: matched",
            )
        elif status == STATUS_MISMATCH:
            outcome = DimensionOutcome(
                name="financial",
                status=STATUS_MISMATCH,
                detail=validation.mismatch_summary
                or "Invoice ↔ PO financial validation reported a mismatch.",
                mismatched_entry="Invoice financial validation: mismatch"
                + (f" ({validation.mismatch_summary})" if validation.mismatch_summary else ""),
            )
        else:
            outcome = DimensionOutcome(
                name="financial",
                status=STATUS_NEEDS_REVIEW,
                detail=validation.mismatch_summary
                or "Invoice ↔ PO financial validation needs review.",
                missing_entry="Invoice financial validation: needs review",
            )
        return outcome, validation.id, validation.status

    def _relationship_dimension(
        self,
        invoice_doc: Document,
        po_doc: Document,
        grn_doc: Document,
    ) -> DimensionOutcome:
        present: list[str] = []
        missing: list[str] = []
        checks = [
            (
                DocumentRelationshipType.INVOICE_PURCHASE_ORDER.value,
                invoice_doc.id,
                po_doc.id,
                "invoice_purchase_order",
            ),
            (
                DocumentRelationshipType.GOODS_RECEIPT_PURCHASE_ORDER.value,
                grn_doc.id,
                po_doc.id,
                "goods_receipt_purchase_order",
            ),
            (
                DocumentRelationshipType.INVOICE_GOODS_RECEIPT.value,
                invoice_doc.id,
                grn_doc.id,
                "invoice_goods_receipt",
            ),
        ]
        for relationship_type, source_id, target_id, label in checks:
            if self._has_relationship(source_id, target_id, relationship_type):
                present.append(label)
            else:
                missing.append(label)

        if missing:
            return DimensionOutcome(
                name="relationships",
                status=STATUS_NEEDS_REVIEW,
                detail=(
                    "Required document relationships are missing: "
                    + ", ".join(missing)
                    + ". Confirm relationships before treating this as a complete 3-way match."
                ),
                missing_entry="Relationships: missing " + ", ".join(missing),
            )
        return DimensionOutcome(
            name="relationships",
            status=STATUS_MATCHED,
            detail="Required document relationships are present: " + ", ".join(present),
            matched_entry="Relationships: " + ", ".join(present),
        )

    def _has_relationship(
        self,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        relationship_type: str,
    ) -> bool:
        row = self.db.scalar(
            select(DocumentRelationship.id).where(
                DocumentRelationship.relationship_type == relationship_type,
                or_(
                    (
                        (DocumentRelationship.source_document_id == source_id)
                        & (DocumentRelationship.target_document_id == target_id)
                    ),
                    (
                        (DocumentRelationship.source_document_id == target_id)
                        & (DocumentRelationship.target_document_id == source_id)
                    ),
                ),
            )
        )
        return row is not None

    @staticmethod
    def _resolve_overall(dimensions: list[DimensionOutcome]) -> str:
        if any(item.status == STATUS_MISMATCH for item in dimensions):
            return STATUS_MISMATCH
        if any(item.status in {STATUS_NEEDS_REVIEW, STATUS_NOT_EVALUABLE} for item in dimensions):
            return STATUS_NEEDS_REVIEW
        if all(item.status == STATUS_MATCHED for item in dimensions):
            return STATUS_MATCHED
        return STATUS_NEEDS_REVIEW

    @staticmethod
    def _confidence(status: str, dimensions: list[DimensionOutcome]) -> float:
        """Transparent confidence from overall status and share of matched dimensions."""
        matched_count = sum(1 for item in dimensions if item.status == STATUS_MATCHED)
        ratio = matched_count / len(dimensions) if dimensions else 0.0
        if status == STATUS_MATCHED:
            return round(0.85 + 0.1 * ratio, 2)
        if status == STATUS_MISMATCH:
            return round(0.25 + 0.2 * ratio, 2)
        return round(0.45 + 0.2 * ratio, 2)

    @staticmethod
    def _build_explanation(
        status: str,
        dimensions: list[DimensionOutcome],
        quantity_evidence: list[dict],
    ) -> str:
        lines = [f"Status: {status}"]
        matched = [item for item in dimensions if item.status == STATUS_MATCHED]
        mismatched = [item for item in dimensions if item.status == STATUS_MISMATCH]
        missing = [
            item
            for item in dimensions
            if item.status in {STATUS_NEEDS_REVIEW, STATUS_NOT_EVALUABLE}
        ]
        if matched:
            lines.append("Matched:")
            for item in matched:
                lines.append(f"- {item.detail or item.name}")
        if mismatched:
            lines.append("Mismatches:")
            for item in mismatched:
                lines.append(f"- {item.detail or item.name}")
        if missing:
            lines.append("Missing / Not evaluated:")
            for item in missing:
                lines.append(f"- {item.detail or item.name}")
        if quantity_evidence:
            lines.append("Quantity line evidence:")
            for item in quantity_evidence:
                label = item.get("item_code") or item.get("description") or item.get("item_key")
                lines.append(
                    f"- {label}: PO={item.get('po_quantity')} GRN={item.get('grn_quantity')} "
                    f"Invoice={item.get('invoice_quantity')} [{item.get('status')}]"
                )
        lines.append(
            "This is an assistive validation result only. It does not approve, reject, "
            "or block payment."
        )
        return "\n".join(lines)

    def _upsert_result(
        self,
        payload: ThreeWayMatchRequest,
        computation: MatchComputation,
    ) -> ThreeWayMatch:
        existing = self.db.scalar(
            select(ThreeWayMatch).where(
                ThreeWayMatch.invoice_document_id == payload.invoice_document_id,
                ThreeWayMatch.purchase_order_document_id == payload.purchase_order_document_id,
                ThreeWayMatch.goods_receipt_document_id == payload.goods_receipt_document_id,
            )
        )
        now = datetime.now(timezone.utc)
        if existing is None:
            existing = ThreeWayMatch(
                invoice_document_id=payload.invoice_document_id,
                purchase_order_document_id=payload.purchase_order_document_id,
                goods_receipt_document_id=payload.goods_receipt_document_id,
                created_at=now,
            )
            self.db.add(existing)

        existing.status = computation.status
        existing.overall_confidence = computation.overall_confidence
        existing.vendor_status = computation.vendor.status
        existing.po_reference_status = computation.po_reference.status
        existing.grn_reference_status = computation.grn_reference.status
        existing.quantity_status = computation.quantity.status
        existing.financial_status = computation.financial.status
        existing.relationship_status = computation.relationships.status
        existing.matched_fields = computation.matched_fields
        existing.mismatched_fields = computation.mismatched_fields
        existing.missing_fields = computation.missing_fields
        existing.dimension_details = {
            "vendor": computation.vendor.detail,
            "po_reference": computation.po_reference.detail,
            "grn_reference": computation.grn_reference.detail,
            "quantity": computation.quantity.detail,
            "financial": computation.financial.detail,
            "relationships": computation.relationships.detail,
        }
        existing.quantity_evidence = computation.quantity_evidence
        existing.explanation = computation.explanation
        existing.invoice_po_validation_id = computation.invoice_po_validation_id
        existing.updated_at = now
        self.db.flush()
        return existing

    def _maybe_create_review(self, invoice_doc: Document, computation: MatchComputation) -> None:
        if computation.status == STATUS_MATCHED:
            return
        if computation.status == STATUS_MISMATCH:
            reason = ReviewReason.THREE_WAY_MATCH_MISMATCH.value
            priority = ReviewPriority.HIGH.value
            details = "Three-way matching reported a mismatch. " + (
                computation.explanation or ""
            )
        else:
            reason = ReviewReason.THREE_WAY_MATCH_NEEDS_REVIEW.value
            priority = ReviewPriority.MEDIUM.value
            details = "Three-way matching needs human review. " + (computation.explanation or "")

        DocumentReviewService(self.db).safe_create_review_if_needed(
            document_id=invoice_doc.id,
            reason=reason,
            priority=priority,
            details=details.strip(),
        )

    def _response_for_row(self, row: ThreeWayMatch) -> ThreeWayMatchResponse:
        invoice_doc = self.db.get(Document, row.invoice_document_id)
        po_doc = self.db.get(Document, row.purchase_order_document_id)
        grn_doc = self.db.get(Document, row.goods_receipt_document_id)
        invoice = self.db.scalar(
            select(Invoice).where(Invoice.document_id == row.invoice_document_id)
        )
        purchase_order = self.db.scalar(
            select(PurchaseOrder).where(PurchaseOrder.document_id == row.purchase_order_document_id)
        )
        goods_receipt = self.db.scalar(
            select(GoodsReceipt).where(GoodsReceipt.document_id == row.goods_receipt_document_id)
        )
        validation_status = None
        if row.invoice_po_validation_id:
            from app.models.validation import DocumentValidation

            validation = self.db.get(DocumentValidation, row.invoice_po_validation_id)
            validation_status = validation.status if validation else None
        return self._to_response(
            row,
            invoice_doc=invoice_doc,
            po_doc=po_doc,
            grn_doc=grn_doc,
            invoice=invoice,
            purchase_order=purchase_order,
            goods_receipt=goods_receipt,
            invoice_po_validation_status=validation_status,
        )

    @staticmethod
    def _to_response(
        row: ThreeWayMatch,
        *,
        invoice_doc: Document | None,
        po_doc: Document | None,
        grn_doc: Document | None,
        invoice: Invoice | None,
        purchase_order: PurchaseOrder | None,
        goods_receipt: GoodsReceipt | None,
        invoice_po_validation_status: str | None,
    ) -> ThreeWayMatchResponse:
        details = row.dimension_details if isinstance(row.dimension_details, dict) else {}
        dimensions = [
            ThreeWayDimensionResult(
                name="vendor",
                status=row.vendor_status,
                detail=details.get("vendor"),
            ),
            ThreeWayDimensionResult(
                name="po_reference",
                status=row.po_reference_status,
                detail=details.get("po_reference"),
            ),
            ThreeWayDimensionResult(
                name="grn_reference",
                status=row.grn_reference_status,
                detail=details.get("grn_reference"),
            ),
            ThreeWayDimensionResult(
                name="quantity",
                status=row.quantity_status,
                detail=details.get("quantity"),
            ),
            ThreeWayDimensionResult(
                name="financial",
                status=row.financial_status,
                detail=details.get("financial"),
            ),
            ThreeWayDimensionResult(
                name="relationships",
                status=row.relationship_status,
                detail=details.get("relationships"),
            ),
        ]
        return ThreeWayMatchResponse(
            id=row.id,
            status=row.status,
            overall_confidence=row.overall_confidence,
            invoice_document_id=row.invoice_document_id,
            purchase_order_document_id=row.purchase_order_document_id,
            goods_receipt_document_id=row.goods_receipt_document_id,
            invoice=ThreeWayDocumentSummary(
                document_id=row.invoice_document_id,
                document_type=invoice_doc.document_type if invoice_doc else None,
                filename=invoice_doc.original_filename if invoice_doc else None,
                record_id=invoice.id if invoice else None,
                number=invoice.invoice_number if invoice else None,
                vendor_name=invoice.vendor_name if invoice else None,
            ),
            purchase_order=ThreeWayDocumentSummary(
                document_id=row.purchase_order_document_id,
                document_type=po_doc.document_type if po_doc else None,
                filename=po_doc.original_filename if po_doc else None,
                record_id=purchase_order.id if purchase_order else None,
                number=purchase_order.po_number if purchase_order else None,
                vendor_name=purchase_order.vendor_name if purchase_order else None,
            ),
            goods_receipt=ThreeWayDocumentSummary(
                document_id=row.goods_receipt_document_id,
                document_type=grn_doc.document_type if grn_doc else None,
                filename=grn_doc.original_filename if grn_doc else None,
                record_id=goods_receipt.id if goods_receipt else None,
                number=goods_receipt.grn_number if goods_receipt else None,
                vendor_name=goods_receipt.vendor_name if goods_receipt else None,
            ),
            vendor_status=row.vendor_status,
            po_reference_status=row.po_reference_status,
            grn_reference_status=row.grn_reference_status,
            quantity_status=row.quantity_status,
            financial_status=row.financial_status,
            relationship_status=row.relationship_status,
            dimensions=dimensions,
            matched_fields=list(row.matched_fields or []),
            mismatched_fields=list(row.mismatched_fields or []),
            missing_fields=list(row.missing_fields or []),
            quantity_evidence=[
                ThreeWayQuantityEvidenceItem(**item)
                for item in (row.quantity_evidence or [])
                if isinstance(item, dict)
            ],
            explanation=row.explanation or "",
            invoice_po_validation_id=row.invoice_po_validation_id,
            invoice_po_validation_status=invoice_po_validation_status,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
