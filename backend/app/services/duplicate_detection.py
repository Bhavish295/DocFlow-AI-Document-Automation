"""Multi-level duplicate detection for documents and invoices."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import logging
from math import ceil
from typing import Any
import uuid

from sqlalchemy import and_, asc, desc, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppError
from app.models.document import Document
from app.models.duplicate import DocumentDuplicate, DuplicateDetectionType, DuplicateStatus
from app.models.invoice import Invoice
from app.services.duplicate_similarity import (
    passes_similarity_threshold,
    similarity_between_documents,
)


ALLOWED_DUPLICATE_STATUSES = {item.value for item in DuplicateStatus}
ALLOWED_DETECTION_TYPES = {item.value for item in DuplicateDetectionType}


def normalize_pair(left: uuid.UUID, right: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    """Order UUIDs so reverse pairs collapse to one canonical pair."""
    if left == right:
        raise AppError("A document cannot be a duplicate of itself.", status_code=400)
    if str(left) <= str(right):
        return left, right
    return right, left


def _normalize_vendor(name: str | None) -> str | None:
    if not name or not str(name).strip():
        return None
    return " ".join(str(name).strip().lower().split())


def _normalize_invoice_number(value: str | None) -> str | None:
    if not value or not str(value).strip():
        return None
    return "".join(ch for ch in str(value).strip().upper() if ch.isalnum())


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


logger = logging.getLogger(__name__)


class DuplicateDetectionService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def check_document(self, document_id: uuid.UUID) -> dict[str, Any]:
        document = self.db.get(Document, document_id)
        if document is None:
            raise AppError("Document not found.", status_code=404)

        created: list[DocumentDuplicate] = []
        created.extend(self._detect_exact(document))
        created.extend(self._detect_business(document))
        created.extend(self._detect_similar(document))
        self.db.commit()

        items = self.list_for_document(document_id)["items"]
        return {
            "document_id": document_id,
            "created_count": len(created),
            "items": items,
            "summary": self.summary_for_document(document_id),
        }

    def safe_check_document(self, document_id: uuid.UUID) -> dict[str, Any] | None:
        """Run duplicate detection after processing; never fails the processing pipeline."""
        if not settings.DUPLICATE_AUTO_CHECK_ENABLED:
            return None
        try:
            return self.check_document(document_id)
        except Exception:
            logger.exception("Automatic duplicate check failed for document %s", document_id)
            self.db.rollback()
            return None

    def _detect_exact(self, document: Document) -> list[DocumentDuplicate]:
        if not document.content_hash:
            return []
        matches = self.db.scalars(
            select(Document).where(
                Document.content_hash == document.content_hash,
                Document.id != document.id,
            )
        ).all()
        created: list[DocumentDuplicate] = []
        for match in matches:
            record = self._upsert_pair(
                document.id,
                match.id,
                detection_type=DuplicateDetectionType.EXACT_DUPLICATE.value,
                similarity_score=1.0,
                confidence=1.0,
                reasons=[
                    "Identical SHA-256 content hash.",
                    "Files have the same binary content regardless of filename.",
                ],
            )
            if record is not None:
                created.append(record)
        return created

    def _detect_business(self, document: Document) -> list[DocumentDuplicate]:
        invoice = self.db.scalar(select(Invoice).where(Invoice.document_id == document.id))
        if invoice is None:
            return []

        vendor_key = _normalize_vendor(invoice.vendor_name)
        invoice_number = _normalize_invoice_number(invoice.invoice_number)
        if not vendor_key or not invoice_number:
            return []

        # Prefer indexed vendor_id when available; otherwise require non-null identifiers.
        filters = [
            Invoice.document_id != document.id,
            Invoice.invoice_number.isnot(None),
            Invoice.vendor_name.isnot(None),
        ]
        if invoice.vendor_id is not None:
            filters.append(Invoice.vendor_id == invoice.vendor_id)

        candidates = self.db.scalars(select(Invoice).where(*filters)).all()
        created: list[DocumentDuplicate] = []
        tolerance = Decimal(str(settings.DUPLICATE_BUSINESS_AMOUNT_TOLERANCE))

        for other in candidates:
            other_vendor = _normalize_vendor(other.vendor_name)
            other_number = _normalize_invoice_number(other.invoice_number)
            if other_vendor != vendor_key or other_number != invoice_number:
                continue

            reasons = [
                "Same normalized vendor name and invoice number.",
            ]
            confidence = 0.85
            similarity = 0.9

            same_currency = bool(
                invoice.currency
                and other.currency
                and invoice.currency.strip().upper() == other.currency.strip().upper()
            )
            if same_currency:
                reasons.append("Same currency.")
                confidence += 0.05
                similarity += 0.03

            left_total = _to_decimal(invoice.total_amount)
            right_total = _to_decimal(other.total_amount)
            if left_total is not None and right_total is not None:
                if abs(left_total - right_total) <= tolerance:
                    reasons.append("Same total amount within configured tolerance.")
                    confidence += 0.05
                    similarity += 0.04

            if invoice.invoice_date and other.invoice_date and invoice.invoice_date == other.invoice_date:
                reasons.append("Same invoice date.")
                confidence += 0.05
                similarity += 0.03

            record = self._upsert_pair(
                document.id,
                other.document_id,
                detection_type=DuplicateDetectionType.BUSINESS_DUPLICATE.value,
                similarity_score=min(1.0, round(similarity, 4)),
                confidence=min(1.0, round(confidence, 4)),
                reasons=reasons,
            )
            if record is not None:
                created.append(record)
        return created

    def _detect_similar(self, document: Document) -> list[DocumentDuplicate]:
        from app.models.document_chunk import DocumentChunk

        has_text = bool(document.extracted_text and document.extracted_text.strip())
        has_embeddings = (
            self.db.scalar(
                select(func.count())
                .select_from(DocumentChunk)
                .where(DocumentChunk.document_id == document.id)
            )
            or 0
        ) > 0
        if not has_text and not has_embeddings:
            return []

        filters = [Document.id != document.id]
        if document.document_type:
            filters.append(
                or_(
                    Document.document_type == document.document_type,
                    Document.document_type.is_(None),
                )
            )

        query = select(Document).where(*filters).order_by(Document.uploaded_at.desc())
        candidates = list(
            self.db.scalars(query.limit(settings.DUPLICATE_MAX_SIMILARITY_CANDIDATES * 3)).all()
        )

        invoice = self.db.scalar(select(Invoice).where(Invoice.document_id == document.id))
        vendor_key = _normalize_vendor(invoice.vendor_name) if invoice else None
        ranked: list[tuple[Document, float]] = []
        for candidate in candidates:
            score = 0.0
            if document.document_type and candidate.document_type == document.document_type:
                score += 2.0
            if vendor_key:
                other_invoice = self.db.scalar(
                    select(Invoice).where(Invoice.document_id == candidate.id)
                )
                if other_invoice and _normalize_vendor(other_invoice.vendor_name) == vendor_key:
                    score += 3.0
            ranked.append((candidate, score))
        ranked.sort(key=lambda item: item[1], reverse=True)
        shortlist = [item[0] for item in ranked[: settings.DUPLICATE_MAX_SIMILARITY_CANDIDATES]]

        created: list[DocumentDuplicate] = []
        for candidate in shortlist:
            similarity, method = similarity_between_documents(self.db, document, candidate)
            if not passes_similarity_threshold(similarity):
                continue
            reasons = [
                f"Content similarity score {similarity:.2f} using {method}.",
                "Similarity is a signal only and does not prove duplication.",
            ]
            if document.document_type and candidate.document_type == document.document_type:
                reasons.append(f"Both documents are typed as '{document.document_type}'.")
            record = self._upsert_pair(
                document.id,
                candidate.id,
                detection_type=DuplicateDetectionType.SIMILAR_DUPLICATE.value,
                similarity_score=similarity,
                confidence=round(min(0.95, max(0.5, similarity)), 4),
                reasons=reasons,
            )
            if record is not None:
                created.append(record)
        return created

    def _upsert_pair(
        self,
        left_id: uuid.UUID,
        right_id: uuid.UUID,
        *,
        detection_type: str,
        similarity_score: float | None,
        confidence: float | None,
        reasons: list[str],
    ) -> DocumentDuplicate | None:
        source_id, duplicate_id = normalize_pair(left_id, right_id)
        existing = self.db.scalar(
            select(DocumentDuplicate).where(
                DocumentDuplicate.source_document_id == source_id,
                DocumentDuplicate.duplicate_document_id == duplicate_id,
                DocumentDuplicate.detection_type == detection_type,
            )
        )
        now = datetime.now(timezone.utc)
        if existing is not None:
            # Refresh evidence but do not flip a human resolution unless still pending.
            existing.similarity_score = similarity_score
            existing.confidence = confidence
            existing.reasons = reasons
            if existing.status == DuplicateStatus.PENDING.value:
                existing.detected_at = now
            self.db.flush()
            return None

        record = DocumentDuplicate(
            source_document_id=source_id,
            duplicate_document_id=duplicate_id,
            detection_type=detection_type,
            similarity_score=similarity_score,
            confidence=confidence,
            reasons=reasons,
            status=DuplicateStatus.PENDING.value,
            detected_at=now,
        )
        self.db.add(record)
        self.db.flush()
        return record

    def list_duplicates(
        self,
        *,
        status: str | None = None,
        detection_type: str | None = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "detected_at",
        sort_order: str = "desc",
    ) -> dict[str, Any]:
        if page < 1:
            raise AppError("page must be >= 1.", status_code=400)
        if page_size < 1 or page_size > 100:
            raise AppError("page_size must be between 1 and 100.", status_code=400)

        sort_map = {
            "detected_at": DocumentDuplicate.detected_at,
            "similarity_score": DocumentDuplicate.similarity_score,
            "confidence": DocumentDuplicate.confidence,
            "status": DocumentDuplicate.status,
            "detection_type": DocumentDuplicate.detection_type,
        }
        sort_column = sort_map.get((sort_by or "detected_at").lower())
        if sort_column is None:
            raise AppError("Invalid sort_by.", status_code=400)
        order = (sort_order or "desc").lower()
        if order not in {"asc", "desc"}:
            raise AppError("Invalid sort_order.", status_code=400)

        filters = []
        if status:
            normalized = status.strip().lower()
            if normalized not in ALLOWED_DUPLICATE_STATUSES:
                raise AppError("Invalid status.", status_code=400)
            filters.append(DocumentDuplicate.status == normalized)
        if detection_type:
            normalized = detection_type.strip().lower()
            if normalized not in ALLOWED_DETECTION_TYPES:
                raise AppError("Invalid detection_type.", status_code=400)
            filters.append(DocumentDuplicate.detection_type == normalized)

        count_stmt = select(func.count()).select_from(DocumentDuplicate)
        stmt = select(DocumentDuplicate)
        if filters:
            count_stmt = count_stmt.where(*filters)
            stmt = stmt.where(*filters)

        total = self.db.scalar(count_stmt) or 0
        order_expr = asc(sort_column) if order == "asc" else desc(sort_column)
        rows = self.db.scalars(
            stmt.order_by(order_expr, desc(DocumentDuplicate.id))
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        total_pages = ceil(total / page_size) if total else 0
        return {
            "items": [self._to_result(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    def list_for_document(self, document_id: uuid.UUID) -> dict[str, Any]:
        document = self.db.get(Document, document_id)
        if document is None:
            raise AppError("Document not found.", status_code=404)
        rows = self.db.scalars(
            select(DocumentDuplicate)
            .where(
                or_(
                    DocumentDuplicate.source_document_id == document_id,
                    DocumentDuplicate.duplicate_document_id == document_id,
                )
            )
            .order_by(desc(DocumentDuplicate.detected_at))
        ).all()
        return {
            "document_id": document_id,
            "items": [self._to_result(row, perspective_document_id=document_id) for row in rows],
            "total": len(rows),
        }

    def resolve_duplicate(self, duplicate_id: uuid.UUID, status: str) -> dict[str, Any]:
        normalized = (status or "").strip().lower()
        if normalized not in ALLOWED_DUPLICATE_STATUSES:
            raise AppError(
                "Invalid status. Allowed values: pending, confirmed, dismissed.",
                status_code=400,
            )
        record = self.db.get(DocumentDuplicate, duplicate_id)
        if record is None:
            raise AppError("Duplicate record not found.", status_code=404)
        record.status = normalized
        if normalized in {DuplicateStatus.CONFIRMED.value, DuplicateStatus.DISMISSED.value}:
            record.resolved_at = datetime.now(timezone.utc)
        else:
            record.resolved_at = None
        self.db.commit()
        self.db.refresh(record)
        return self._to_result(record)

    def summary(self) -> dict[str, Any]:
        def _count(*, detection_type: str | None = None, status: str | None = None) -> int:
            stmt = select(func.count()).select_from(DocumentDuplicate)
            filters = []
            if detection_type:
                filters.append(DocumentDuplicate.detection_type == detection_type)
            if status:
                filters.append(DocumentDuplicate.status == status)
            if filters:
                stmt = stmt.where(*filters)
            return int(self.db.scalar(stmt) or 0)

        return {
            "exact": _count(detection_type=DuplicateDetectionType.EXACT_DUPLICATE.value),
            "business": _count(detection_type=DuplicateDetectionType.BUSINESS_DUPLICATE.value),
            "similar": _count(detection_type=DuplicateDetectionType.SIMILAR_DUPLICATE.value),
            "pending": _count(status=DuplicateStatus.PENDING.value),
            "confirmed": _count(status=DuplicateStatus.CONFIRMED.value),
            "dismissed": _count(status=DuplicateStatus.DISMISSED.value),
            "total": _count(),
        }

    def summary_for_document(self, document_id: uuid.UUID) -> dict[str, Any]:
        rows = self.db.scalars(
            select(DocumentDuplicate).where(
                or_(
                    DocumentDuplicate.source_document_id == document_id,
                    DocumentDuplicate.duplicate_document_id == document_id,
                )
            )
        ).all()
        summary = {
            "exact": 0,
            "business": 0,
            "similar": 0,
            "pending": 0,
            "confirmed": 0,
            "dismissed": 0,
            "total": len(rows),
        }
        for row in rows:
            if row.detection_type == DuplicateDetectionType.EXACT_DUPLICATE.value:
                summary["exact"] += 1
            elif row.detection_type == DuplicateDetectionType.BUSINESS_DUPLICATE.value:
                summary["business"] += 1
            elif row.detection_type == DuplicateDetectionType.SIMILAR_DUPLICATE.value:
                summary["similar"] += 1
            if row.status in summary:
                summary[row.status] += 1
        return summary

    def count_for_documents(self, document_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        if not document_ids:
            return {}
        rows = self.db.execute(
            select(
                DocumentDuplicate.source_document_id,
                DocumentDuplicate.duplicate_document_id,
            ).where(
                or_(
                    DocumentDuplicate.source_document_id.in_(document_ids),
                    DocumentDuplicate.duplicate_document_id.in_(document_ids),
                ),
                DocumentDuplicate.status != DuplicateStatus.DISMISSED.value,
            )
        ).all()
        counts: dict[uuid.UUID, int] = {document_id: 0 for document_id in document_ids}
        for source_id, duplicate_id in rows:
            if source_id in counts:
                counts[source_id] += 1
            if duplicate_id in counts:
                counts[duplicate_id] += 1
        return counts

    def _to_result(
        self,
        record: DocumentDuplicate,
        *,
        perspective_document_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        source = self.db.get(Document, record.source_document_id)
        duplicate = self.db.get(Document, record.duplicate_document_id)
        matched = duplicate
        if perspective_document_id is not None:
            if record.source_document_id == perspective_document_id:
                matched = duplicate
            else:
                matched = source
        return {
            "id": record.id,
            "source_document_id": record.source_document_id,
            "duplicate_document_id": record.duplicate_document_id,
            "matched_document_id": matched.id if matched else None,
            "matched_filename": matched.original_filename if matched else None,
            "matched_document_type": matched.document_type if matched else None,
            "source_filename": source.original_filename if source else None,
            "duplicate_filename": duplicate.original_filename if duplicate else None,
            "detection_type": record.detection_type,
            "similarity_score": record.similarity_score,
            "confidence": record.confidence,
            "reasons": record.reasons or [],
            "status": record.status,
            "detected_at": record.detected_at,
            "resolved_at": record.resolved_at,
        }
