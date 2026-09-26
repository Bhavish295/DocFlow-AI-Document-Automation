"""Provider-neutral email attachment ingestion interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


@dataclass
class NormalizedEmailAttachment:
    provider: str
    message_id: str
    sender: str | None
    subject: str | None
    received_at: datetime | None
    filename: str
    content: bytes
    content_type: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class EmailAttachmentProvider(Protocol):
    """Future IMAP / Gmail / Graph adapters implement this protocol."""

    def fetch_attachments(self) -> list[NormalizedEmailAttachment]:
        """Return normalized attachments without credentials in the payload."""


def build_email_source_identity(*, provider: str, message_id: str, filename: str) -> str:
    """Deterministic identity for duplicate email-attachment protection."""
    return (
        f"{provider.strip().lower()}:"
        f"{message_id.strip()}:"
        f"{filename.strip().lower()}"
    )
