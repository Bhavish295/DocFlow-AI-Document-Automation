"""Application logging configuration (no secrets in log output)."""

from __future__ import annotations

import logging
import re
import sys

from app.core.config import settings

_SECRET_PATTERNS = (
    re.compile(r"(password\s*[=:]\s*)\S+", re.IGNORECASE),
    re.compile(r"(passwd\s*[=:]\s*)\S+", re.IGNORECASE),
    re.compile(r"(secret\s*[=:]\s*)\S+", re.IGNORECASE),
    re.compile(r"(authorization\s*[=:]\s*bearer\s+)\S+", re.IGNORECASE),
    re.compile(r"(api[_-]?key\s*[=:]\s*)\S+", re.IGNORECASE),
    re.compile(r"(token\s*[=:]\s*)\S+", re.IGNORECASE),
)


class _RedactFilter(logging.Filter):
    """Best-effort scrubbing of common secret patterns from log messages."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True
        redacted = message
        for pattern in _SECRET_PATTERNS:
            redacted = pattern.sub(r"\1[REDACTED]", redacted)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


def configure_logging() -> None:
    """Configure root logging for development or production."""
    level_name = "DEBUG" if settings.is_development and settings.DEBUG else "INFO"
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.addFilter(_RedactFilter())
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    root.addHandler(handler)

    # Quiet noisy libraries in production
    if settings.is_production:
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
