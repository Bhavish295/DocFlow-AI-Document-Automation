"""Provider-independent document ingestion (batch, email, manual)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from io import BytesIO
from pathlib import Path
import base64
import uuid

from fastapi import BackgroundTasks, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.storage import sanitize_original_filename
from app.models.document_ingestion import (
    DocumentIngestion,
    IngestionSourceType,
    IngestionStatus,
)
from app.schemas.ingestion import (
    BatchIngestionItemResult,
    BatchIngestionResponse,
    EmailAttachmentIngestRequest,
    EmailAttachmentIngestResponse,
    IngestionListResponse,
    IngestionResponse,
)
from app.services.audit_service import AuditService
from app.services.document import DocumentService
from app.services.document_processing_orchestrator import DocumentProcessingOrchestrator
from app.services.email_attachment_provider import (
    NormalizedEmailAttachment,
    build_email_source_identity,
)
from app.services.text_extraction import PROCESSABLE_FILE_TYPES


SECRET_METADATA_KEYS = {
    "password",
    "passwd",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "apikey",
    "secret",
    "authorization",
    "credential",
    "credentials",
}


def _sanitize_metadata(raw: dict | None) -> dict | None:
    if not raw:
        return None
    cleaned: dict = {}
    for key, value in raw.items():
        key_l = str(key).lower()
        if key_l in SECRET_METADATA_KEYS or any(part in key_l for part in ("password", "token", "secret", "api_key")):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            cleaned[str(key)] = value
        else:
            cleaned[str(key)] = str(value)[:500]
    return cleaned or None


def _safe_error(exc: BaseException | str) -> str:
    text = str(exc).strip() if not isinstance(exc, str) else exc.strip()
    return (text.splitlines()[0] if text else "Ingestion failed.")[:500]


class DocumentIngestionService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.documents = DocumentService(db)
        self.audit = AuditService(db)

    def to_response(self, row: DocumentIngestion) -> IngestionResponse:
        return IngestionResponse(
            id=row.id,
            source_type=row.source_type,
            source_reference=row.source_reference,
            original_filename=row.original_filename,
            document_id=row.document_id,
            processing_job_id=row.processing_job_id,
            status=row.status,
            error_message=row.error_message,
            metadata=row.metadata_json,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def get_ingestion(self, ingestion_id: uuid.UUID) -> IngestionResponse:
        row = self.db.get(DocumentIngestion, ingestion_id)
        if row is None:
            raise AppError("Ingestion record not found.", status_code=404)
        return self.to_response(row)

    def list_ingestions(
        self,
        *,
        source_type: str | None = None,
        status: str | None = None,
        created_from: date | None = None,
        created_to: date | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> IngestionListResponse:
        page = max(1, page)
        page_size = min(100, max(1, page_size))
        query = select(DocumentIngestion)
        if source_type:
            query = query.where(DocumentIngestion.source_type == source_type)
        if status:
            query = query.where(DocumentIngestion.status == status)
        if created_from:
            query = query.where(
                DocumentIngestion.created_at >= datetime.combine(created_from, datetime.min.time(), tzinfo=timezone.utc)
            )
        if created_to:
            query = query.where(
                DocumentIngestion.created_at
                <= datetime.combine(created_to, datetime.max.time(), tzinfo=timezone.utc)
            )

        total = self.db.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = list(
            self.db.scalars(
                query.order_by(DocumentIngestion.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        return IngestionListResponse(
            items=[self.to_response(row) for row in rows],
            total=int(total),
            page=page,
            page_size=page_size,
        )

    def ingest_upload(
        self,
        file: UploadFile,
        *,
        source_type: str,
        source_reference: str | None = None,
        source_identity: str | None = None,
        metadata: dict | None = None,
        actor_id: uuid.UUID | None = None,
        background_tasks: BackgroundTasks | None = None,
        queue_processing: bool = True,
    ) -> IngestionResponse:
        try:
            filename = sanitize_original_filename(file.filename)
        except AppError as exc:
            now = datetime.now(timezone.utc)
            display = Path(file.filename or "upload.bin").name[:200] or "upload.bin"
            row = DocumentIngestion(
                source_type=source_type,
                source_reference=source_reference,
                source_identity=source_identity,
                original_filename=display,
                status=IngestionStatus.FAILED.value,
                error_message=_safe_error(exc.message),
                metadata_json=_sanitize_metadata(metadata),
                created_at=now,
                updated_at=now,
            )
            self.db.add(row)
            self.db.commit()
            self.db.refresh(row)
            self.audit.log(
                action="ingestion_failed",
                user_id=actor_id,
                resource_type="ingestion",
                resource_id=row.id,
                details={"filename": display, "error": row.error_message},
            )
            return self.to_response(row)

        if source_identity:
            existing = self.db.scalar(
                select(DocumentIngestion).where(DocumentIngestion.source_identity == source_identity)
            )
            if existing is not None:
                self.audit.log(
                    action="duplicate_email_attachment_skipped",
                    user_id=actor_id,
                    resource_type="ingestion",
                    resource_id=existing.id,
                    details={"filename": filename, "source_identity": source_identity},
                )
                return IngestionResponse(
                    id=existing.id,
                    source_type=existing.source_type,
                    source_reference=existing.source_reference,
                    original_filename=existing.original_filename,
                    document_id=existing.document_id,
                    processing_job_id=existing.processing_job_id,
                    status=IngestionStatus.SKIPPED.value,
                    error_message="Already ingested from the same email attachment source.",
                    metadata=existing.metadata_json,
                    created_at=existing.created_at,
                    updated_at=existing.updated_at,
                )

        now = datetime.now(timezone.utc)
        row = DocumentIngestion(
            source_type=source_type,
            source_reference=source_reference,
            source_identity=source_identity,
            original_filename=filename,
            status=IngestionStatus.PROCESSING.value,
            metadata_json=_sanitize_metadata(metadata),
            created_at=now,
            updated_at=now,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)

        try:
            document = self.documents.create_document(file)
            row.document_id = document.id
            row.updated_at = datetime.now(timezone.utc)

            job_id: uuid.UUID | None = None
            if queue_processing and document.file_type.lower() in PROCESSABLE_FILE_TYPES:
                process_result = DocumentProcessingOrchestrator(self.db).enqueue_process(
                    document.id,
                    background_tasks=background_tasks,
                )
                job_id = process_result.job_id

            row.processing_job_id = job_id
            row.status = IngestionStatus.COMPLETED.value
            row.error_message = None
            row.updated_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(row)

            self.audit.log(
                action="document_ingested",
                user_id=actor_id,
                resource_type="ingestion",
                resource_id=row.id,
                details={
                    "source_type": source_type,
                    "filename": filename,
                    "document_id": str(document.id),
                },
            )
            return self.to_response(row)
        except AppError as exc:
            row.status = IngestionStatus.FAILED.value
            row.error_message = _safe_error(exc.message)
            row.updated_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(row)
            self.audit.log(
                action="ingestion_failed",
                user_id=actor_id,
                resource_type="ingestion",
                resource_id=row.id,
                details={"filename": filename, "error": row.error_message},
            )
            return self.to_response(row)
        except Exception as exc:  # noqa: BLE001
            row.status = IngestionStatus.FAILED.value
            row.error_message = _safe_error(exc)
            row.updated_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(row)
            self.audit.log(
                action="ingestion_failed",
                user_id=actor_id,
                resource_type="ingestion",
                resource_id=row.id,
                details={"filename": filename, "error": row.error_message},
            )
            return self.to_response(row)

    def ingest_bytes(
        self,
        *,
        filename: str,
        content: bytes,
        content_type: str | None = None,
        source_type: str,
        source_reference: str | None = None,
        source_identity: str | None = None,
        metadata: dict | None = None,
        actor_id: uuid.UUID | None = None,
        background_tasks: BackgroundTasks | None = None,
        queue_processing: bool = True,
    ) -> IngestionResponse:
        upload = UploadFile(
            filename=filename,
            file=BytesIO(content),
        )
        return self.ingest_upload(
            upload,
            source_type=source_type,
            source_reference=source_reference,
            source_identity=source_identity,
            metadata=metadata,
            actor_id=actor_id,
            background_tasks=background_tasks,
            queue_processing=queue_processing,
        )

    def ingest_batch(
        self,
        files: list[UploadFile],
        *,
        actor_id: uuid.UUID | None = None,
        background_tasks: BackgroundTasks | None = None,
        queue_processing: bool = True,
    ) -> BatchIngestionResponse:
        max_files = settings.INGESTION_MAX_BATCH_FILES
        if len(files) == 0:
            raise AppError("At least one file is required.", status_code=400)
        if len(files) > max_files:
            raise AppError(
                f"Batch exceeds the maximum of {max_files} files.",
                status_code=400,
            )

        self.audit.log(
            action="batch_ingestion_started",
            user_id=actor_id,
            resource_type="ingestion",
            details={"file_count": len(files)},
        )

        items: list[BatchIngestionItemResult] = []
        accepted = failed = skipped = 0
        for file in files:
            try:
                filename = sanitize_original_filename(file.filename)
            except AppError as exc:
                failed += 1
                items.append(
                    BatchIngestionItemResult(
                        filename=Path(file.filename or "upload.bin").name,
                        status=IngestionStatus.FAILED.value,
                        error=exc.message,
                    )
                )
                continue
            try:
                result = self.ingest_upload(
                    file,
                    source_type=IngestionSourceType.BATCH_UPLOAD.value,
                    source_reference="batch",
                    metadata={"batch": True},
                    actor_id=actor_id,
                    background_tasks=background_tasks,
                    queue_processing=queue_processing,
                )
                if result.status == IngestionStatus.SKIPPED.value:
                    skipped += 1
                elif result.status == IngestionStatus.FAILED.value:
                    failed += 1
                else:
                    accepted += 1
                items.append(
                    BatchIngestionItemResult(
                        filename=filename,
                        ingestion_id=result.id,
                        document_id=result.document_id,
                        processing_job_id=result.processing_job_id,
                        status=result.status,
                        error=result.error_message,
                    )
                )
            except AppError as exc:
                failed += 1
                items.append(
                    BatchIngestionItemResult(
                        filename=filename,
                        status=IngestionStatus.FAILED.value,
                        error=_safe_error(exc.message),
                    )
                )
            except Exception as exc:  # noqa: BLE001
                failed += 1
                items.append(
                    BatchIngestionItemResult(
                        filename=filename,
                        status=IngestionStatus.FAILED.value,
                        error=_safe_error(exc),
                    )
                )

        return BatchIngestionResponse(
            total=len(items),
            accepted=accepted,
            failed=failed,
            skipped=skipped,
            items=items,
        )

    def ingest_email_attachment(
        self,
        attachment: NormalizedEmailAttachment,
        *,
        actor_id: uuid.UUID | None = None,
        background_tasks: BackgroundTasks | None = None,
        queue_processing: bool = True,
    ) -> EmailAttachmentIngestResponse:
        identity = build_email_source_identity(
            provider=attachment.provider,
            message_id=attachment.message_id,
            filename=attachment.filename,
        )
        existing = self.db.scalar(
            select(DocumentIngestion).where(DocumentIngestion.source_identity == identity)
        )
        if existing is not None:
            self.audit.log(
                action="duplicate_email_attachment_skipped",
                user_id=actor_id,
                resource_type="ingestion",
                resource_id=existing.id,
                details={"filename": attachment.filename, "message_id": attachment.message_id},
            )
            return EmailAttachmentIngestResponse(
                filename=attachment.filename,
                ingestion_id=existing.id,
                document_id=existing.document_id,
                processing_job_id=existing.processing_job_id,
                status=IngestionStatus.SKIPPED.value,
                error="Already ingested from the same email attachment source.",
                already_ingested=True,
            )

        metadata = {
            "provider": attachment.provider,
            "message_id": attachment.message_id,
            "sender": attachment.sender,
            "subject": attachment.subject,
            "received_at": attachment.received_at.isoformat() if attachment.received_at else None,
            "content_type": attachment.content_type,
        }
        if attachment.metadata:
            metadata.update(attachment.metadata)

        result = self.ingest_bytes(
            filename=attachment.filename,
            content=attachment.content,
            content_type=attachment.content_type,
            source_type=IngestionSourceType.EMAIL_ATTACHMENT.value,
            source_reference=attachment.message_id,
            source_identity=identity,
            metadata=metadata,
            actor_id=actor_id,
            background_tasks=background_tasks,
            queue_processing=queue_processing,
        )

        if result.status == IngestionStatus.COMPLETED.value:
            self.audit.log(
                action="email_attachment_ingested",
                user_id=actor_id,
                resource_type="ingestion",
                resource_id=result.id,
                details={
                    "filename": attachment.filename,
                    "message_id": attachment.message_id,
                    "provider": attachment.provider,
                },
            )

        return EmailAttachmentIngestResponse(
            filename=attachment.filename,
            ingestion_id=result.id,
            document_id=result.document_id,
            processing_job_id=result.processing_job_id,
            status=result.status,
            error=result.error_message,
            already_ingested=False,
        )

    def ingest_email_request(
        self,
        payload: EmailAttachmentIngestRequest,
        *,
        actor_id: uuid.UUID | None = None,
        background_tasks: BackgroundTasks | None = None,
        queue_processing: bool = True,
    ) -> EmailAttachmentIngestResponse:
        try:
            content = base64.b64decode(payload.content_base64, validate=True)
        except Exception as exc:  # noqa: BLE001
            raise AppError("Invalid base64 attachment content.", status_code=400) from exc
        if not content:
            raise AppError("Attachment content is empty.", status_code=400)

        attachment = NormalizedEmailAttachment(
            provider=payload.provider,
            message_id=payload.message_id,
            sender=payload.sender,
            subject=payload.subject,
            received_at=payload.received_at,
            filename=sanitize_original_filename(payload.filename),
            content=content,
            content_type=payload.content_type,
            metadata=payload.metadata or {},
        )
        return self.ingest_email_attachment(
            attachment,
            actor_id=actor_id,
            background_tasks=background_tasks,
            queue_processing=queue_processing,
        )
