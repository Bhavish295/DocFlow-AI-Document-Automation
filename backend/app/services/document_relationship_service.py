"""Deterministic document relationship management (no auto payment actions)."""

from __future__ import annotations

from datetime import datetime, timezone
import re
import uuid

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.models.document import Document, DocumentType
from app.models.document_relationship import (
    DocumentRelationship,
    DocumentRelationshipStatus,
    DocumentRelationshipType,
)
from app.models.goods_receipt import GoodsReceipt
from app.models.invoice import Invoice
from app.models.purchase_order import PurchaseOrder
from app.schemas.document_relationship import (
    DocumentRelationshipCreate,
    DocumentRelationshipListResponse,
    DocumentRelationshipResponse,
    DocumentRelationshipSuggestion,
    DocumentRelationshipSuggestionListResponse,
)


RELATIONSHIP_TYPE_RULES: dict[str, tuple[str, str]] = {
    DocumentRelationshipType.INVOICE_PURCHASE_ORDER.value: (
        DocumentType.INVOICE.value,
        DocumentType.PURCHASE_ORDER.value,
    ),
    DocumentRelationshipType.GOODS_RECEIPT_PURCHASE_ORDER.value: (
        DocumentType.GOODS_RECEIPT.value,
        DocumentType.PURCHASE_ORDER.value,
    ),
    DocumentRelationshipType.INVOICE_GOODS_RECEIPT.value: (
        DocumentType.INVOICE.value,
        DocumentType.GOODS_RECEIPT.value,
    ),
}

DISPLAY_LABELS = {
    DocumentRelationshipType.INVOICE_PURCHASE_ORDER.value: "Invoice → Purchase Order",
    DocumentRelationshipType.GOODS_RECEIPT_PURCHASE_ORDER.value: "Goods Receipt → Purchase Order",
    DocumentRelationshipType.INVOICE_GOODS_RECEIPT.value: "Invoice → Goods Receipt",
}

PO_NUMBER_PATTERNS = [
    r"(?:purchase\s+order\s*(?:number|no\.?)|p\.?\s*o\.?\s*(?:number|no\.?|#)|"
    r"po\s*(?:number|no\.?|#))\s*[:#-]?\s*([A-Z0-9][A-Z0-9 /\-]{1,40})",
]
GRN_NUMBER_PATTERNS = [
    r"(?:grn\s*(?:number|no\.?|#)|g\.?r\.?n\.?\s*(?:number|no\.?|#))\s*[:#-]?\s*"
    r"([A-Z0-9][A-Z0-9 /\-]{1,40})",
    r"(?:goods\s+receipt\s+(?:note\s+)?(?:number|no\.?|#)|receipt\s+no\.?)\s*[:#-]?\s*"
    r"([A-Z0-9][A-Z0-9 /\-]{1,40})",
]


def normalize_match_key(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"\s+", "", value.strip().upper())
    return cleaned or None


def extract_labeled_number(text: str | None, patterns: list[str]) -> str | None:
    if not text:
        return None
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip(" :-#")
    return None


class DocumentRelationshipService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_relationship(self, payload: DocumentRelationshipCreate) -> DocumentRelationshipResponse:
        if payload.source_document_id == payload.target_document_id:
            raise AppError("A document cannot be related to itself.", status_code=400)

        relationship_type = (payload.relationship_type or "").strip().lower()
        if relationship_type not in RELATIONSHIP_TYPE_RULES:
            raise AppError(
                "Unsupported relationship type. Allowed: "
                + ", ".join(sorted(RELATIONSHIP_TYPE_RULES)),
                status_code=400,
            )

        source = self._get_document_or_404(payload.source_document_id)
        target = self._get_document_or_404(payload.target_document_id)
        expected_source, expected_target = RELATIONSHIP_TYPE_RULES[relationship_type]
        if source.document_type != expected_source or target.document_type != expected_target:
            raise AppError(
                f"Relationship type '{relationship_type}' requires "
                f"source={expected_source} and target={expected_target}.",
                status_code=400,
            )

        existing = self._find_existing(
            payload.source_document_id,
            payload.target_document_id,
            relationship_type,
        )
        if existing is not None:
            raise AppError("This document relationship already exists.", status_code=409)

        reverse = self._find_existing(
            payload.target_document_id,
            payload.source_document_id,
            relationship_type,
        )
        if reverse is not None:
            raise AppError("This document relationship already exists.", status_code=409)

        now = datetime.now(timezone.utc)
        row = DocumentRelationship(
            source_document_id=payload.source_document_id,
            target_document_id=payload.target_document_id,
            relationship_type=relationship_type,
            status=DocumentRelationshipStatus.CONFIRMED.value,
            match_key=normalize_match_key(payload.match_key) or payload.match_key,
            created_at=now,
            updated_at=now,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return self._to_response(row, perspective_document_id=None)

    def list_relationships(
        self,
        *,
        document_id: uuid.UUID | None = None,
    ) -> DocumentRelationshipListResponse:
        stmt = select(DocumentRelationship).order_by(DocumentRelationship.created_at.desc())
        if document_id is not None:
            stmt = stmt.where(
                or_(
                    DocumentRelationship.source_document_id == document_id,
                    DocumentRelationship.target_document_id == document_id,
                )
            )
        rows = list(self.db.scalars(stmt).all())
        items = [self._to_response(row, perspective_document_id=document_id) for row in rows]
        return DocumentRelationshipListResponse(items=items, total=len(items))

    def get_for_document(self, document_id: uuid.UUID) -> DocumentRelationshipListResponse:
        self._get_document_or_404(document_id)
        return self.list_relationships(document_id=document_id)

    def delete_relationship(self, relationship_id: uuid.UUID) -> None:
        row = self.db.get(DocumentRelationship, relationship_id)
        if row is None:
            raise AppError("Document relationship not found.", status_code=404)
        self.db.delete(row)
        self.db.commit()

    def suggest_for_document(
        self,
        document_id: uuid.UUID,
    ) -> DocumentRelationshipSuggestionListResponse:
        document = self._get_document_or_404(document_id)
        existing_pairs = {
            (
                row.relationship_type,
                frozenset({row.source_document_id, row.target_document_id}),
            )
            for row in self.db.scalars(
                select(DocumentRelationship).where(
                    or_(
                        DocumentRelationship.source_document_id == document_id,
                        DocumentRelationship.target_document_id == document_id,
                    )
                )
            ).all()
        }

        suggestions: list[DocumentRelationshipSuggestion] = []
        doc_type = document.document_type

        if doc_type == DocumentType.INVOICE.value:
            suggestions.extend(self._suggest_invoice_to_po(document, existing_pairs))
            suggestions.extend(self._suggest_invoice_to_grn(document, existing_pairs))
        elif doc_type == DocumentType.PURCHASE_ORDER.value:
            suggestions.extend(self._suggest_po_to_invoice(document, existing_pairs))
            suggestions.extend(self._suggest_po_to_grn(document, existing_pairs))
        elif doc_type == DocumentType.GOODS_RECEIPT.value:
            suggestions.extend(self._suggest_grn_to_po(document, existing_pairs))
            suggestions.extend(self._suggest_grn_to_invoice(document, existing_pairs))

        return DocumentRelationshipSuggestionListResponse(
            document_id=document_id,
            items=suggestions,
            total=len(suggestions),
        )

    def _suggest_invoice_to_po(
        self,
        invoice_doc: Document,
        existing_pairs: set[tuple[str, frozenset]],
    ) -> list[DocumentRelationshipSuggestion]:
        po_key = self._invoice_po_number(invoice_doc)
        if not po_key:
            return []
        items: list[DocumentRelationshipSuggestion] = []
        for po, po_doc in self._purchase_orders_by_number(po_key):
            items.append(
                self._suggestion(
                    relationship_type=DocumentRelationshipType.INVOICE_PURCHASE_ORDER.value,
                    source=invoice_doc,
                    target=po_doc,
                    match_key=po.po_number or po_key,
                    match_field="po_number",
                    existing_pairs=existing_pairs,
                )
            )
        return items

    def _suggest_invoice_to_grn(
        self,
        invoice_doc: Document,
        existing_pairs: set[tuple[str, frozenset]],
    ) -> list[DocumentRelationshipSuggestion]:
        grn_key = self._invoice_grn_number(invoice_doc)
        if not grn_key:
            return []
        items: list[DocumentRelationshipSuggestion] = []
        for grn, grn_doc in self._goods_receipts_by_number(grn_key):
            items.append(
                self._suggestion(
                    relationship_type=DocumentRelationshipType.INVOICE_GOODS_RECEIPT.value,
                    source=invoice_doc,
                    target=grn_doc,
                    match_key=grn.grn_number or grn_key,
                    match_field="grn_number",
                    existing_pairs=existing_pairs,
                )
            )
        return items

    def _suggest_po_to_invoice(
        self,
        po_doc: Document,
        existing_pairs: set[tuple[str, frozenset]],
    ) -> list[DocumentRelationshipSuggestion]:
        po = self.db.scalar(select(PurchaseOrder).where(PurchaseOrder.document_id == po_doc.id))
        if po is None or not po.po_number:
            return []
        key = normalize_match_key(po.po_number)
        items: list[DocumentRelationshipSuggestion] = []
        for invoice_doc in self._documents_of_type(DocumentType.INVOICE.value):
            if normalize_match_key(self._invoice_po_number(invoice_doc)) != key:
                continue
            items.append(
                self._suggestion(
                    relationship_type=DocumentRelationshipType.INVOICE_PURCHASE_ORDER.value,
                    source=invoice_doc,
                    target=po_doc,
                    match_key=po.po_number,
                    match_field="po_number",
                    existing_pairs=existing_pairs,
                )
            )
        return items

    def _suggest_po_to_grn(
        self,
        po_doc: Document,
        existing_pairs: set[tuple[str, frozenset]],
    ) -> list[DocumentRelationshipSuggestion]:
        po = self.db.scalar(select(PurchaseOrder).where(PurchaseOrder.document_id == po_doc.id))
        if po is None or not po.po_number:
            return []
        items: list[DocumentRelationshipSuggestion] = []
        for grn, grn_doc in self._goods_receipts_by_number(po.po_number, field="po_number"):
            items.append(
                self._suggestion(
                    relationship_type=DocumentRelationshipType.GOODS_RECEIPT_PURCHASE_ORDER.value,
                    source=grn_doc,
                    target=po_doc,
                    match_key=po.po_number,
                    match_field="po_number",
                    existing_pairs=existing_pairs,
                )
            )
        return items

    def _suggest_grn_to_po(
        self,
        grn_doc: Document,
        existing_pairs: set[tuple[str, frozenset]],
    ) -> list[DocumentRelationshipSuggestion]:
        grn = self.db.scalar(select(GoodsReceipt).where(GoodsReceipt.document_id == grn_doc.id))
        if grn is None or not grn.po_number:
            return []
        items: list[DocumentRelationshipSuggestion] = []
        for po, po_doc in self._purchase_orders_by_number(grn.po_number):
            items.append(
                self._suggestion(
                    relationship_type=DocumentRelationshipType.GOODS_RECEIPT_PURCHASE_ORDER.value,
                    source=grn_doc,
                    target=po_doc,
                    match_key=po.po_number or grn.po_number,
                    match_field="po_number",
                    existing_pairs=existing_pairs,
                )
            )
        return items

    def _suggest_grn_to_invoice(
        self,
        grn_doc: Document,
        existing_pairs: set[tuple[str, frozenset]],
    ) -> list[DocumentRelationshipSuggestion]:
        grn = self.db.scalar(select(GoodsReceipt).where(GoodsReceipt.document_id == grn_doc.id))
        if grn is None or not grn.grn_number:
            return []
        key = normalize_match_key(grn.grn_number)
        items: list[DocumentRelationshipSuggestion] = []
        for invoice_doc in self._documents_of_type(DocumentType.INVOICE.value):
            if normalize_match_key(self._invoice_grn_number(invoice_doc)) != key:
                continue
            items.append(
                self._suggestion(
                    relationship_type=DocumentRelationshipType.INVOICE_GOODS_RECEIPT.value,
                    source=invoice_doc,
                    target=grn_doc,
                    match_key=grn.grn_number,
                    match_field="grn_number",
                    existing_pairs=existing_pairs,
                )
            )
        return items

    def _suggestion(
        self,
        *,
        relationship_type: str,
        source: Document,
        target: Document,
        match_key: str,
        match_field: str,
        existing_pairs: set[tuple[str, frozenset]],
    ) -> DocumentRelationshipSuggestion:
        pair = (relationship_type, frozenset({source.id, target.id}))
        return DocumentRelationshipSuggestion(
            relationship_type=relationship_type,
            source_document_id=source.id,
            target_document_id=target.id,
            match_key=match_key,
            match_field=match_field,
            source_filename=source.original_filename,
            target_filename=target.original_filename,
            source_document_type=source.document_type,
            target_document_type=target.document_type,
            status="suggested",
            already_linked=pair in existing_pairs,
        )

    def _invoice_po_number(self, document: Document) -> str | None:
        return extract_labeled_number(document.extracted_text, PO_NUMBER_PATTERNS)

    def _invoice_grn_number(self, document: Document) -> str | None:
        return extract_labeled_number(document.extracted_text, GRN_NUMBER_PATTERNS)

    def _purchase_orders_by_number(
        self,
        raw_number: str,
    ) -> list[tuple[PurchaseOrder, Document]]:
        key = normalize_match_key(raw_number)
        if not key:
            return []
        rows = self.db.scalars(select(PurchaseOrder)).all()
        results: list[tuple[PurchaseOrder, Document]] = []
        for po in rows:
            if normalize_match_key(po.po_number) != key:
                continue
            doc = self.db.get(Document, po.document_id)
            if doc is not None:
                results.append((po, doc))
        return results

    def _goods_receipts_by_number(
        self,
        raw_number: str,
        *,
        field: str = "grn_number",
    ) -> list[tuple[GoodsReceipt, Document]]:
        key = normalize_match_key(raw_number)
        if not key:
            return []
        rows = self.db.scalars(select(GoodsReceipt)).all()
        results: list[tuple[GoodsReceipt, Document]] = []
        for grn in rows:
            value = grn.grn_number if field == "grn_number" else grn.po_number
            if normalize_match_key(value) != key:
                continue
            doc = self.db.get(Document, grn.document_id)
            if doc is not None:
                results.append((grn, doc))
        return results

    def _documents_of_type(self, document_type: str) -> list[Document]:
        return list(
            self.db.scalars(select(Document).where(Document.document_type == document_type)).all()
        )

    def _find_existing(
        self,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        relationship_type: str,
    ) -> DocumentRelationship | None:
        return self.db.scalar(
            select(DocumentRelationship).where(
                DocumentRelationship.source_document_id == source_id,
                DocumentRelationship.target_document_id == target_id,
                DocumentRelationship.relationship_type == relationship_type,
            )
        )

    def _get_document_or_404(self, document_id: uuid.UUID) -> Document:
        document = self.db.get(Document, document_id)
        if document is None:
            raise AppError("Document not found.", status_code=404)
        return document

    def _to_response(
        self,
        row: DocumentRelationship,
        *,
        perspective_document_id: uuid.UUID | None,
    ) -> DocumentRelationshipResponse:
        source = self.db.get(Document, row.source_document_id)
        target = self.db.get(Document, row.target_document_id)
        related_id = None
        related_filename = None
        related_type = None
        if perspective_document_id is not None:
            if perspective_document_id == row.source_document_id:
                related_id = row.target_document_id
                related_filename = target.original_filename if target else None
                related_type = target.document_type if target else None
            else:
                related_id = row.source_document_id
                related_filename = source.original_filename if source else None
                related_type = source.document_type if source else None

        return DocumentRelationshipResponse(
            id=row.id,
            source_document_id=row.source_document_id,
            target_document_id=row.target_document_id,
            relationship_type=row.relationship_type,
            status=row.status,
            match_key=row.match_key,
            created_at=row.created_at,
            updated_at=row.updated_at,
            source_filename=source.original_filename if source else None,
            target_filename=target.original_filename if target else None,
            source_document_type=source.document_type if source else None,
            target_document_type=target.document_type if target else None,
            related_document_id=related_id,
            related_filename=related_filename,
            related_document_type=related_type,
            display_label=DISPLAY_LABELS.get(row.relationship_type, row.relationship_type),
        )
