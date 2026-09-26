"""IMAP email attachment provider (stdlib imaplib — no OAuth)."""

from __future__ import annotations

from datetime import datetime, timezone
import email
from email.header import decode_header, make_header
from email.message import Message
import imaplib
import logging
from typing import Any

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.storage import is_allowed_extension
from app.services.email_attachment_provider import NormalizedEmailAttachment

logger = logging.getLogger(__name__)


def _decode_header_value(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(make_header(decode_header(value)))
    except Exception:  # noqa: BLE001
        return value


def _parse_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(raw)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def _message_id(msg: Message) -> str:
    mid = (msg.get("Message-ID") or msg.get("Message-Id") or "").strip()
    if mid:
        return mid.strip("<>").strip()
    # Stable fallback without leaking body content
    subject = _decode_header_value(msg.get("Subject")) or ""
    date = msg.get("Date") or ""
    sender = _decode_header_value(msg.get("From")) or ""
    return f"generated:{hash((sender, subject, date)) & 0xFFFFFFFF:x}"


class ImapEmailAttachmentProvider:
    """
    Provider-neutral IMAP attachment fetcher.

    Credentials are read from settings and never returned in attachment payloads.
    Emails are not deleted or marked processed beyond IMAP fetch semantics.
    """

    provider_name = "imap"

    def __init__(
        self,
        *,
        host: str | None = None,
        port: int | None = None,
        username: str | None = None,
        password: str | None = None,
        folder: str | None = None,
        use_ssl: bool | None = None,
    ) -> None:
        self.host = (host if host is not None else settings.EMAIL_IMAP_HOST) or ""
        self.port = int(port if port is not None else settings.EMAIL_IMAP_PORT or 993)
        self.username = (username if username is not None else settings.EMAIL_IMAP_USERNAME) or ""
        self.password = (password if password is not None else settings.EMAIL_IMAP_PASSWORD) or ""
        self.folder = (folder if folder is not None else settings.EMAIL_IMAP_FOLDER) or "INBOX"
        self.use_ssl = settings.EMAIL_IMAP_USE_SSL if use_ssl is None else use_ssl

    def assert_configured(self) -> None:
        if not self.host.strip() or not self.username.strip() or not self.password:
            raise AppError(
                "IMAP email provider is not configured.",
                status_code=400,
            )

    def fetch_attachments(self) -> list[NormalizedEmailAttachment]:
        self.assert_configured()
        client: imaplib.IMAP4 | imaplib.IMAP4_SSL | None = None
        try:
            if self.use_ssl:
                client = imaplib.IMAP4_SSL(self.host, self.port)
            else:
                client = imaplib.IMAP4(self.host, self.port)
            # Avoid logging credentials — login failures raise without password.
            client.login(self.username, self.password)
            typ, _ = client.select(self.folder, readonly=True)
            if typ != "OK":
                raise AppError(f"Unable to select IMAP folder '{self.folder}'.", status_code=502)

            typ, data = client.search(None, "ALL")
            if typ != "OK" or not data or not data[0]:
                return []

            message_ids = data[0].split()
            # Limit work per poll to keep cycles bounded
            message_ids = message_ids[-100:]
            results: list[NormalizedEmailAttachment] = []
            for num in message_ids:
                try:
                    results.extend(self._attachments_from_message(client, num))
                except Exception:  # noqa: BLE001 - one bad message must not stop the cycle
                    logger.warning("Skipping IMAP message %s due to parse/fetch error", num)
            return results
        except AppError:
            raise
        except imaplib.IMAP4.error as exc:
            logger.warning("IMAP authentication or protocol error: %s", exc.__class__.__name__)
            raise AppError("IMAP connection or authentication failed.", status_code=502) from exc
        except OSError as exc:
            logger.warning("IMAP network error: %s", exc.__class__.__name__)
            raise AppError("IMAP network error.", status_code=502) from exc
        finally:
            if client is not None:
                try:
                    client.logout()
                except Exception:  # noqa: BLE001
                    pass

    def _attachments_from_message(
        self,
        client: imaplib.IMAP4 | imaplib.IMAP4_SSL,
        num: bytes,
    ) -> list[NormalizedEmailAttachment]:
        typ, payload = client.fetch(num, "(RFC822)")
        if typ != "OK" or not payload:
            return []
        raw = None
        for part in payload:
            if isinstance(part, tuple) and len(part) >= 2 and isinstance(part[1], (bytes, bytearray)):
                raw = bytes(part[1])
                break
        if not raw:
            return []

        msg = email.message_from_bytes(raw)
        message_id = _message_id(msg)
        sender = _decode_header_value(msg.get("From"))
        subject = _decode_header_value(msg.get("Subject"))
        received_at = _parse_date(msg.get("Date"))
        attachments: list[NormalizedEmailAttachment] = []

        for part in msg.walk():
            if part.get_content_maintype() == "multipart":
                continue
            disposition = (part.get("Content-Disposition") or "").lower()
            filename = part.get_filename()
            if filename:
                filename = _decode_header_value(filename) or filename
            if not filename and "attachment" not in disposition:
                continue
            if not filename:
                continue
            if not is_allowed_extension(filename):
                logger.info("Skipping unsupported IMAP attachment %s", filename)
                continue
            try:
                content = part.get_payload(decode=True) or b""
            except Exception:  # noqa: BLE001
                logger.warning("Failed to decode attachment payload for %s", filename)
                continue
            if not content:
                continue
            attachments.append(
                NormalizedEmailAttachment(
                    provider=self.provider_name,
                    message_id=message_id,
                    sender=sender,
                    subject=subject,
                    received_at=received_at,
                    filename=filename,
                    content=content,
                    content_type=part.get_content_type(),
                    metadata={
                        "imap_folder": self.folder,
                        "has_attachment": True,
                    },
                )
            )
        return attachments


def get_email_attachment_provider() -> Any | None:
    """Return a configured provider instance, or None when disabled."""
    name = settings.email_provider_name
    if name in {"", "none"}:
        return None
    if name == "mock":
        from app.services.mock_email_provider import MockEmailAttachmentProvider

        return MockEmailAttachmentProvider()
    if name == "imap":
        return ImapEmailAttachmentProvider()
    raise AppError(f"Unknown EMAIL_PROVIDER '{name}'.", status_code=400)
