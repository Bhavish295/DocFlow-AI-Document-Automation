from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.storage import (
    ensure_upload_dir,
    get_extension,
    resolve_file_type,
    sanitize_original_filename,
    validate_upload_header,
)
from app.models.document import Document, DocumentStatus
from app.models.document_review import ACTIVE_REVIEW_STATUSES, DocumentReview
from app.models.goods_receipt import GoodsReceipt
from app.models.invoice import Invoice
from app.models.purchase_order import PurchaseOrder
from app.schemas.document import DocumentListResponse, DocumentResponse
from app.services.document_search import DocumentSearchService


CHUNK_SIZE = 1024 * 1024
HEADER_SNIFF_BYTES = 16


class DocumentService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_document(self, file: UploadFile) -> DocumentResponse:
        safe_name = sanitize_original_filename(file.filename)
        extension = get_extension(safe_name)

        upload_dir = ensure_upload_dir()
        document_id = uuid.uuid4()
        stored_filename = f"{document_id}{extension}"
        destination = upload_dir / stored_filename

        # Never use client-provided names as storage paths.
        if destination.resolve().parent != upload_dir.resolve():
            raise AppError("Invalid storage destination.", status_code=400)

        file_size = 0
        header = b""
        header_checked = False
        try:
            with destination.open("wb") as buffer:
                while True:
                    chunk = file.file.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    if not header_checked:
                        header = chunk[:HEADER_SNIFF_BYTES]
                        validate_upload_header(
                            extension,
                            header,
                            content_type=getattr(file, "content_type", None),
                        )
                        header_checked = True
                    file_size += len(chunk)
                    if file_size > settings.max_upload_bytes:
                        raise AppError(
                            f"File exceeds the maximum size of {settings.MAX_UPLOAD_SIZE_MB} MB.",
                            status_code=413,
                        )
                    buffer.write(chunk)
        except AppError:
            self._remove_file(destination)
            raise
        except Exception as exc:
            self._remove_file(destination)
            raise AppError("Failed to store uploaded file.", status_code=500) from exc
        finally:
            file.file.close()

        if file_size == 0:
            self._remove_file(destination)
            raise AppError("Uploaded file is empty.", status_code=400)

        from app.services.document_hashing import sha256_file

        content_hash = sha256_file(destination)

        document = Document(
            id=document_id,
            original_filename=safe_name,
            stored_filename=stored_filename,
            file_type=resolve_file_type(safe_name),
            file_size=file_size,
            storage_path=str(destination),
            content_hash=content_hash,
            status=DocumentStatus.UPLOADED.value,
        )

        try:
            self.db.add(document)
            self.db.commit()
            self.db.refresh(document)
        except Exception as exc:
            self.db.rollback()
            self._remove_file(destination)
            raise AppError("Failed to save document metadata.", status_code=500) from exc

        return self._to_response(document)

    def list_documents(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        document_type: str | None = None,
        status: str | None = None,
        uploaded_from: date | None = None,
        uploaded_to: date | None = None,
        sort_by: str = "uploaded_at",
        sort_order: str = "desc",
    ) -> DocumentListResponse:
        documents, total, total_pages, has_next, has_previous = DocumentSearchService(
            self.db
        ).search_documents(
            search=search,
            document_type=document_type,
            status=status,
            uploaded_from=uploaded_from,
            uploaded_to=uploaded_to,
            sort_by=sort_by,
            sort_order=sort_order,
            page=page,
            page_size=page_size,
        )
        return DocumentListResponse(
            items=[self._to_response(document) for document in documents],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_next=has_next,
            has_previous=has_previous,
        )

    def get_document(self, document_id: uuid.UUID) -> DocumentResponse:
        document = self._get_document_or_404(document_id)
        return self._to_response(document)

    def delete_document(self, document_id: uuid.UUID) -> None:
        document = self._get_document_or_404(document_id)
        storage_path = Path(document.storage_path)
        self.db.delete(document)
        try:
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            raise AppError("Failed to delete document.", status_code=500) from exc
        self._remove_file(storage_path)

    def _get_document_or_404(self, document_id: uuid.UUID) -> Document:
        document = self.db.get(Document, document_id)
        if document is None:
            raise AppError("Document not found.", status_code=404)
        return document

    @staticmethod
    def _remove_file(path: Path) -> None:
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass

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
