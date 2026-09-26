from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppError
from app.models.invoice import Invoice
from app.models.purchase_order import PurchaseOrder
from app.models.validation import DocumentValidation, ValidationStatus
from app.schemas.validation import ValidationListResponse, ValidationResponse
from app.services.document_review import DocumentReviewService
from app.services.invoice_extraction import normalize_currency


@dataclass
class FieldComparison:
    name: str
    match: bool | None
    summary: str | None = None


class ValidationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.amount_tolerance = Decimal(str(settings.VALIDATION_AMOUNT_TOLERANCE))

    def validate_invoice_against_po(
        self,
        invoice_id: uuid.UUID,
        purchase_order_id: uuid.UUID,
        *,
        commit: bool = True,
        create_review: bool = True,
    ) -> ValidationResponse:
        invoice = self.db.get(Invoice, invoice_id)
        if invoice is None:
            raise AppError("Invoice not found.", status_code=404)

        purchase_order = self.db.get(PurchaseOrder, purchase_order_id)
        if purchase_order is None:
            raise AppError("Purchase order not found.", status_code=404)

        comparisons = [
            self._compare_vendor(invoice.vendor_name, purchase_order.vendor_name),
            self._compare_currency(invoice.currency, purchase_order.currency),
            self._compare_amount("Subtotal", invoice.subtotal, purchase_order.subtotal),
            self._compare_amount("Tax", invoice.tax_amount, purchase_order.tax_amount),
            self._compare_amount("Total", invoice.total_amount, purchase_order.total_amount),
        ]

        status = self._resolve_status(comparisons)
        mismatch_parts = [item.summary for item in comparisons if item.summary]
        mismatch_summary = "; ".join(mismatch_parts) if mismatch_parts else None

        validation = self._get_existing(invoice_id, purchase_order_id)
        now = datetime.now(timezone.utc)
        if validation is None:
            validation = DocumentValidation(
                invoice_id=invoice_id,
                purchase_order_id=purchase_order_id,
                created_at=now,
            )
            self.db.add(validation)

        validation.status = status.value
        validation.vendor_match = comparisons[0].match
        validation.currency_match = comparisons[1].match
        validation.subtotal_match = comparisons[2].match
        validation.tax_match = comparisons[3].match
        validation.total_match = comparisons[4].match
        validation.invoice_number = invoice.invoice_number
        validation.po_number = purchase_order.po_number
        validation.mismatch_summary = mismatch_summary
        validation.updated_at = now

        if create_review and status == ValidationStatus.MISMATCH:
            DocumentReviewService(self.db).create_validation_mismatch_review(
                document_id=invoice.document_id,
                mismatch_summary=mismatch_summary,
            )

        if commit:
            self.db.commit()
            self.db.refresh(validation)
            from app.services.workflow_engine import safe_dispatch_workflow_event

            safe_dispatch_workflow_event(
                self.db,
                trigger_event="validation_completed",
                entity_type="validation",
                entity_id=validation.id,
                metadata={"status": validation.status},
            )
        else:
            self.db.flush()
            self.db.refresh(validation)
        return self._to_response(validation, invoice, purchase_order)

    def get_validation(self, validation_id: uuid.UUID) -> ValidationResponse:
        validation = self.db.get(DocumentValidation, validation_id)
        if validation is None:
            raise AppError("Validation not found.", status_code=404)
        invoice = self.db.get(Invoice, validation.invoice_id)
        purchase_order = self.db.get(PurchaseOrder, validation.purchase_order_id)
        return self._to_response(validation, invoice, purchase_order)

    def list_validations(self, page: int = 1, page_size: int = 50) -> ValidationListResponse:
        if page < 1:
            raise AppError("page must be >= 1.", status_code=400)
        if page_size < 1 or page_size > 100:
            raise AppError("page_size must be between 1 and 100.", status_code=400)

        total = self.db.scalar(select(func.count()).select_from(DocumentValidation)) or 0
        rows = self.db.scalars(
            select(DocumentValidation)
            .order_by(DocumentValidation.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()

        items = []
        for validation in rows:
            invoice = self.db.get(Invoice, validation.invoice_id)
            purchase_order = self.db.get(PurchaseOrder, validation.purchase_order_id)
            items.append(self._to_response(validation, invoice, purchase_order))

        return ValidationListResponse(items=items, total=total, page=page, page_size=page_size)

    def _get_existing(
        self,
        invoice_id: uuid.UUID,
        purchase_order_id: uuid.UUID,
    ) -> DocumentValidation | None:
        return self.db.scalar(
            select(DocumentValidation).where(
                DocumentValidation.invoice_id == invoice_id,
                DocumentValidation.purchase_order_id == purchase_order_id,
            )
        )

    def _compare_vendor(self, invoice_vendor: str | None, po_vendor: str | None) -> FieldComparison:
        if not invoice_vendor or not po_vendor:
            return FieldComparison(
                "Vendor",
                None,
                "Vendor needs review: missing vendor on invoice or PO",
            )
        left = self._normalize_vendor(invoice_vendor)
        right = self._normalize_vendor(po_vendor)
        if left == right:
            return FieldComparison("Vendor", True)
        return FieldComparison(
            "Vendor",
            False,
            f"Vendor mismatch: Invoice {invoice_vendor} vs PO {po_vendor}",
        )

    def _compare_currency(self, invoice_currency: str | None, po_currency: str | None) -> FieldComparison:
        if not invoice_currency or not po_currency:
            return FieldComparison(
                "Currency",
                None,
                "Currency needs review: missing currency on invoice or PO",
            )
        left = normalize_currency(invoice_currency) or invoice_currency.upper()
        right = normalize_currency(po_currency) or po_currency.upper()
        if left == right:
            return FieldComparison("Currency", True)
        return FieldComparison(
            "Currency",
            False,
            f"Currency mismatch: Invoice {left} vs PO {right}",
        )

    def _compare_amount(self, label: str, invoice_amount, po_amount) -> FieldComparison:
        left = self._to_decimal(invoice_amount)
        right = self._to_decimal(po_amount)
        if left is None or right is None:
            return FieldComparison(
                label,
                None,
                f"{label} needs review: missing value on invoice or PO",
            )
        if abs(left - right) <= self.amount_tolerance:
            return FieldComparison(label, True)
        return FieldComparison(
            label,
            False,
            f"{label} mismatch: Invoice {left:.2f} vs PO {right:.2f}",
        )

    @staticmethod
    def _resolve_status(comparisons: list[FieldComparison]) -> ValidationStatus:
        matches = [item.match for item in comparisons]
        if any(value is False for value in matches):
            return ValidationStatus.MISMATCH
        if any(value is None for value in matches):
            return ValidationStatus.NEEDS_REVIEW
        return ValidationStatus.MATCHED

    @staticmethod
    def _normalize_vendor(value: str) -> str:
        normalized = value.strip().lower()
        normalized = re.sub(r"[^\w\s]", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized.strip()

    @staticmethod
    def _to_decimal(value) -> Decimal | None:
        if value is None:
            return None
        return Decimal(str(value)).quantize(Decimal("0.01"))

    @staticmethod
    def _to_response(
        validation: DocumentValidation,
        invoice: Invoice | None,
        purchase_order: PurchaseOrder | None,
    ) -> ValidationResponse:
        vendor = None
        if invoice and invoice.vendor_name:
            vendor = invoice.vendor_name
        elif purchase_order and purchase_order.vendor_name:
            vendor = purchase_order.vendor_name

        return ValidationResponse(
            id=validation.id,
            invoice_id=validation.invoice_id,
            purchase_order_id=validation.purchase_order_id,
            status=validation.status,
            vendor_match=validation.vendor_match,
            currency_match=validation.currency_match,
            subtotal_match=validation.subtotal_match,
            tax_match=validation.tax_match,
            total_match=validation.total_match,
            invoice_number=validation.invoice_number,
            po_number=validation.po_number,
            vendor_name=vendor,
            mismatch_summary=validation.mismatch_summary,
            created_at=validation.created_at,
            updated_at=validation.updated_at,
        )
