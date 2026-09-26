"""Email inbox polling — connects IMAP/mock providers to existing ingestion."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import threading
import uuid

from fastapi import BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import BACKEND_ROOT, settings
from app.core.exceptions import AppError
from app.services.audit_service import AuditService
from app.services.document_ingestion_service import DocumentIngestionService
from app.services.email_attachment_provider import NormalizedEmailAttachment
from app.services.imap_email_provider import get_email_attachment_provider

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_memory_status: dict | None = None


class EmailPollStatus(BaseModel):
    provider: str
    configured: bool
    enabled: bool
    last_poll_at: datetime | None = None
    last_success_at: datetime | None = None
    last_error: str | None = None
    processed_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    worker_mode: str = "local"


class EmailPollResult(BaseModel):
    status: str
    provider: str
    configured: bool
    processed: int = 0
    skipped: int = 0
    failed: int = 0
    message: str = ""
    items: list[dict] = Field(default_factory=list)


def _status_path() -> Path:
    path = Path(settings.UPLOAD_DIR)
    if not path.is_absolute():
        path = BACKEND_ROOT / path
    runtime = path.parent / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    return runtime / "email_poll_status.json"


def _load_status() -> dict:
    global _memory_status
    with _lock:
        if _memory_status is not None:
            return dict(_memory_status)
        path = _status_path()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    _memory_status = data
                    return dict(data)
            except Exception:  # noqa: BLE001
                pass
        _memory_status = {}
        return {}


def _save_status(data: dict) -> None:
    global _memory_status
    safe = dict(data)
    # Never persist credentials
    for key in list(safe.keys()):
        lower = str(key).lower()
        if any(token in lower for token in ("password", "secret", "token", "credential")):
            safe.pop(key, None)
    with _lock:
        _memory_status = safe
        try:
            _status_path().write_text(json.dumps(safe, default=str), encoding="utf-8")
        except Exception:  # noqa: BLE001
            logger.warning("Unable to persist email poll status to disk")


def reset_email_poll_status_for_tests() -> None:
    global _memory_status
    with _lock:
        _memory_status = {}
        path = _status_path()
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass


class EmailPollingService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.ingestion = DocumentIngestionService(db)
        self.audit = AuditService(db)

    def get_status(self) -> EmailPollStatus:
        provider = settings.email_provider_name or "none"
        configured = self._is_configured(provider)
        stored = _load_status()

        def _dt(key: str) -> datetime | None:
            raw = stored.get(key)
            if not raw:
                return None
            try:
                return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            except Exception:  # noqa: BLE001
                return None

        return EmailPollStatus(
            provider=provider,
            configured=configured,
            enabled=configured and provider not in {"none", ""},
            last_poll_at=_dt("last_poll_at"),
            last_success_at=_dt("last_success_at"),
            last_error=stored.get("last_error"),
            processed_count=int(stored.get("processed_count") or 0),
            skipped_count=int(stored.get("skipped_count") or 0),
            failed_count=int(stored.get("failed_count") or 0),
            worker_mode=settings.processing_worker_mode,
        )

    def poll(
        self,
        *,
        actor_id: uuid.UUID | None = None,
        background_tasks: BackgroundTasks | None = None,
    ) -> EmailPollResult:
        provider_name = settings.email_provider_name or "none"
        now = datetime.now(timezone.utc)
        stored = _load_status()
        stored["last_poll_at"] = now.isoformat()

        if provider_name in {"none", ""}:
            stored["last_error"] = None
            _save_status(stored)
            return EmailPollResult(
                status="disabled",
                provider=provider_name,
                configured=False,
                message="Email provider is not configured.",
            )

        if provider_name == "imap" and not settings.email_imap_configured:
            stored["last_error"] = "IMAP is not fully configured."
            _save_status(stored)
            return EmailPollResult(
                status="not_configured",
                provider=provider_name,
                configured=False,
                message="IMAP host/username/password are required.",
            )

        try:
            provider = get_email_attachment_provider()
        except AppError as exc:
            stored["last_error"] = exc.message
            _save_status(stored)
            return EmailPollResult(
                status="error",
                provider=provider_name,
                configured=False,
                message=exc.message,
            )

        if provider is None:
            stored["last_error"] = None
            _save_status(stored)
            return EmailPollResult(
                status="disabled",
                provider=provider_name,
                configured=False,
                message="Email provider is not configured.",
            )

        try:
            attachments = provider.fetch_attachments()
        except AppError as exc:
            stored["last_error"] = exc.message
            _save_status(stored)
            self.audit.log(
                action="email_poll_failed",
                user_id=actor_id,
                resource_type="ingestion",
                details={"provider": provider_name, "error": exc.message},
            )
            return EmailPollResult(
                status="error",
                provider=provider_name,
                configured=True,
                message=exc.message,
            )
        except Exception as exc:  # noqa: BLE001
            message = "Email poll failed."
            stored["last_error"] = message
            _save_status(stored)
            logger.warning("Email poll failed: %s", exc.__class__.__name__)
            return EmailPollResult(
                status="error",
                provider=provider_name,
                configured=True,
                message=message,
            )

        processed = skipped = failed = 0
        items: list[dict] = []
        for attachment in attachments:
            try:
                result = self._ingest_one(
                    attachment,
                    actor_id=actor_id,
                    background_tasks=background_tasks,
                )
                items.append(result)
                status = result.get("status")
                if status == "completed":
                    processed += 1
                elif status == "skipped":
                    skipped += 1
                else:
                    failed += 1
            except Exception as exc:  # noqa: BLE001 - continue polling cycle
                failed += 1
                items.append(
                    {
                        "filename": attachment.filename,
                        "status": "failed",
                        "error": "Attachment ingestion failed.",
                    }
                )
                logger.warning(
                    "Email attachment failed (%s): %s",
                    attachment.filename,
                    exc.__class__.__name__,
                )

        stored["processed_count"] = int(stored.get("processed_count") or 0) + processed
        stored["skipped_count"] = int(stored.get("skipped_count") or 0) + skipped
        stored["failed_count"] = int(stored.get("failed_count") or 0) + failed
        stored["last_success_at"] = now.isoformat()
        stored["last_error"] = None
        _save_status(stored)

        self.audit.log(
            action="email_poll_completed",
            user_id=actor_id,
            resource_type="ingestion",
            details={
                "provider": provider_name,
                "processed": processed,
                "skipped": skipped,
                "failed": failed,
                "attachment_count": len(attachments),
            },
        )

        return EmailPollResult(
            status="ok",
            provider=provider_name,
            configured=True,
            processed=processed,
            skipped=skipped,
            failed=failed,
            message=f"Polled {len(attachments)} attachment(s).",
            items=items,
        )

    def _ingest_one(
        self,
        attachment: NormalizedEmailAttachment,
        *,
        actor_id: uuid.UUID | None,
        background_tasks: BackgroundTasks | None,
    ) -> dict:
        response = self.ingestion.ingest_email_attachment(
            attachment,
            actor_id=actor_id,
            background_tasks=background_tasks,
            queue_processing=True,
        )
        return {
            "filename": response.filename,
            "status": "skipped" if response.already_ingested else response.status,
            "ingestion_id": str(response.ingestion_id) if response.ingestion_id else None,
            "document_id": str(response.document_id) if response.document_id else None,
            "error": response.error,
            "already_ingested": response.already_ingested,
        }

    @staticmethod
    def _is_configured(provider: str) -> bool:
        if provider == "mock":
            return True
        if provider == "imap":
            return settings.email_imap_configured
        return False
