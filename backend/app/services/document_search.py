from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from math import ceil

from sqlalchemy import Select, asc, desc, func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.models.document import Document, DocumentStatus, DocumentType


ALLOWED_SORT_FIELDS = {
    "uploaded_at": Document.uploaded_at,
    "filename": Document.original_filename,
    "document_type": Document.document_type,
    "status": Document.status,
    "file_size": Document.file_size,
}

ALLOWED_DOCUMENT_TYPES = {item.value for item in DocumentType}
ALLOWED_STATUSES = {item.value for item in DocumentStatus}
ALLOWED_SORT_ORDERS = {"asc", "desc"}


def _day_start(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def _day_after(value: date) -> datetime:
    return _day_start(value) + timedelta(days=1)


class DocumentSearchService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def search_documents(
        self,
        *,
        search: str | None = None,
        document_type: str | None = None,
        status: str | None = None,
        uploaded_from: date | None = None,
        uploaded_to: date | None = None,
        sort_by: str = "uploaded_at",
        sort_order: str = "desc",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Document], int, int, bool, bool]:
        page, page_size = self._validate_pagination(page, page_size)
        sort_column, normalized_order = self._validate_sort(sort_by, sort_order)
        filters = self._build_filters(
            search=search,
            document_type=document_type,
            status=status,
            uploaded_from=uploaded_from,
            uploaded_to=uploaded_to,
        )

        count_stmt = select(func.count()).select_from(Document)
        if filters:
            count_stmt = count_stmt.where(*filters)
        total = self.db.scalar(count_stmt) or 0

        order_expr = asc(sort_column) if normalized_order == "asc" else desc(sort_column)
        query: Select[tuple[Document]] = select(Document)
        if filters:
            query = query.where(*filters)
        query = query.order_by(order_expr, desc(Document.id))

        offset = (page - 1) * page_size
        documents = self.db.scalars(query.offset(offset).limit(page_size)).all()

        total_pages = ceil(total / page_size) if total > 0 else 0
        has_previous = page > 1 and total > 0
        has_next = page < total_pages
        return documents, total, total_pages, has_next, has_previous

    def _build_filters(
        self,
        *,
        search: str | None,
        document_type: str | None,
        status: str | None,
        uploaded_from: date | None,
        uploaded_to: date | None,
    ) -> list:
        filters: list = []

        if search is not None:
            term = " ".join(search.split()).strip()
            if term:
                pattern = f"%{term}%"
                filters.append(
                    or_(
                        Document.original_filename.ilike(pattern),
                        Document.document_type.ilike(pattern),
                        Document.extracted_text.ilike(pattern),
                    )
                )

        if document_type is not None and document_type.strip():
            normalized_type = document_type.strip().lower()
            if normalized_type not in ALLOWED_DOCUMENT_TYPES:
                raise AppError(
                    "Invalid document_type. Allowed values: "
                    + ", ".join(sorted(ALLOWED_DOCUMENT_TYPES)),
                    status_code=400,
                )
            filters.append(Document.document_type == normalized_type)

        if status is not None and status.strip():
            normalized_status = status.strip().lower()
            if normalized_status not in ALLOWED_STATUSES:
                raise AppError(
                    "Invalid status. Allowed values: " + ", ".join(sorted(ALLOWED_STATUSES)),
                    status_code=400,
                )
            filters.append(Document.status == normalized_status)

        if uploaded_from is not None and uploaded_to is not None and uploaded_from > uploaded_to:
            raise AppError("uploaded_from must be on or before uploaded_to.", status_code=400)

        if uploaded_from is not None:
            filters.append(Document.uploaded_at >= _day_start(uploaded_from))

        if uploaded_to is not None:
            # Inclusive end date: keep rows before the next UTC day.
            filters.append(Document.uploaded_at < _day_after(uploaded_to))

        return filters

    @staticmethod
    def _validate_pagination(page: int, page_size: int) -> tuple[int, int]:
        if page < 1:
            raise AppError("page must be >= 1.", status_code=400)
        if page_size < 1 or page_size > 100:
            raise AppError("page_size must be between 1 and 100.", status_code=400)
        return page, page_size

    @staticmethod
    def _validate_sort(sort_by: str, sort_order: str):
        normalized_by = (sort_by or "uploaded_at").strip().lower()
        normalized_order = (sort_order or "desc").strip().lower()
        if normalized_by not in ALLOWED_SORT_FIELDS:
            raise AppError(
                "Invalid sort_by. Allowed values: " + ", ".join(sorted(ALLOWED_SORT_FIELDS)),
                status_code=400,
            )
        if normalized_order not in ALLOWED_SORT_ORDERS:
            raise AppError("Invalid sort_order. Allowed values: asc, desc.", status_code=400)
        return ALLOWED_SORT_FIELDS[normalized_by], normalized_order
