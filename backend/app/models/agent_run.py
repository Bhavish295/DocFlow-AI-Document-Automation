from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, Uuid

from app.core.database import Base


class AgentRun(Base):
    """Persisted controlled-agent execution (no secrets)."""

    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    question: Mapped[str] = mapped_column(String(2000), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    answer: Mapped[str] = mapped_column(Text, nullable=False, default="")
    steps_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    evidence_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    tools_used: Mapped[list | None] = mapped_column(JSON, nullable=True)
    warnings_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    step_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
