"""Deterministic local mock email attachment provider for tests/dev."""

from __future__ import annotations

from datetime import datetime, timezone

from app.services.email_attachment_provider import NormalizedEmailAttachment


MOCK_INVOICE_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<<>>endobj\n"
    b"trailer<<>>\n"
    b"%%EOF\n"
)


class MockEmailAttachmentProvider:
    """Local fixture provider — no network, no credentials."""

    def __init__(self, attachments: list[NormalizedEmailAttachment] | None = None) -> None:
        self._attachments = attachments or [
            NormalizedEmailAttachment(
                provider="mock",
                message_id="mock-message-001",
                sender="vendor@example.test",
                subject="Invoice INV-2001",
                received_at=datetime(2026, 3, 24, 10, 0, tzinfo=timezone.utc),
                filename="invoice_2001.pdf",
                content=MOCK_INVOICE_PDF,
                content_type="application/pdf",
                metadata={"fixture": "step22"},
            )
        ]

    def fetch_attachments(self) -> list[NormalizedEmailAttachment]:
        return list(self._attachments)
