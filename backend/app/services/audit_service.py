"""Reusable audit logging for security-sensitive actions."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import re
import uuid

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


_SECRET_KEY_RE = re.compile(
    r"(password|passwd|secret|token|authorization|api[_-]?key|jwt)",
    re.IGNORECASE,
)


def _scrub_details(details: str | dict | None) -> str | None:
    if details is None:
        return None
    if isinstance(details, str):
        text = details
    else:
        cleaned: dict = {}
        for key, value in details.items():
            if _SECRET_KEY_RE.search(str(key)):
                cleaned[key] = "[REDACTED]"
            else:
                cleaned[key] = value
        text = json.dumps(cleaned, default=str)
    # Never retain bearer tokens / password-like substrings in free text
    text = re.sub(r"(?i)bearer\s+\S+", "Bearer [REDACTED]", text)
    text = re.sub(r"(?i)(password|passwd|secret|token)\s*[:=]\s*\S+", r"\1=[REDACTED]", text)
    return text[:2000]


class AuditService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def log(
        self,
        *,
        action: str,
        user_id: uuid.UUID | None = None,
        resource_type: str | None = None,
        resource_id: str | uuid.UUID | None = None,
        details: str | dict | None = None,
        commit: bool = True,
    ) -> AuditLog:
        row = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            details=_scrub_details(details),
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(row)
        if commit:
            self.db.commit()
            self.db.refresh(row)
        else:
            self.db.flush()
        return row
