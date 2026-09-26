"""Runtime context for a single controlled agent run."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import uuid

from app.models.user import User


@dataclass
class AgentContext:
    user: User
    question: str
    conversation_id: uuid.UUID
    max_steps: int
    evidence: list[dict[str, Any]] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    steps: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    step_count: int = 0
    # Scratch values resolved during planning/execution (never secrets)
    resolved: dict[str, Any] = field(default_factory=dict)

    def add_warning(self, message: str) -> None:
        text = (message or "").strip()
        if text and text not in self.warnings:
            self.warnings.append(text[:500])

    def add_evidence(self, *, source: str, summary: str, details: dict[str, Any] | None = None) -> None:
        self.evidence.append(
            {
                "source": source,
                "summary": summary[:1000],
                "details": _safe_details(details),
            }
        )

    def record_tool(self, tool_name: str) -> None:
        if tool_name not in self.tools_used:
            self.tools_used.append(tool_name)


def _safe_details(details: dict[str, Any] | None) -> dict[str, Any] | None:
    if not details:
        return None
    blocked = ("password", "token", "secret", "authorization", "api_key", "credential", "jwt")
    cleaned: dict[str, Any] = {}
    for key, value in details.items():
        key_l = str(key).lower()
        if any(part in key_l for part in blocked):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            cleaned[str(key)] = value if not isinstance(value, str) else value[:500]
        elif isinstance(value, (list, tuple)):
            cleaned[str(key)] = [str(item)[:200] for item in list(value)[:20]]
        else:
            cleaned[str(key)] = str(value)[:300]
    return cleaned or None
