"""In-process rate limiting for single-instance deployments.

Not distributed — use Redis-backed limiting later for multi-instance production.
"""

from __future__ import annotations

from collections import defaultdict, deque
import threading
import time
from typing import Deque

from fastapi import Request

from app.core.config import settings
from app.core.exceptions import AppError


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits: dict[str, Deque[float]] = defaultdict(deque)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

    def check(self, key: str, *, limit: int, window_seconds: int) -> None:
        if limit <= 0:
            return
        now = time.monotonic()
        window = float(window_seconds)
        with self._lock:
            bucket = self._hits[key]
            while bucket and now - bucket[0] > window:
                bucket.popleft()
            if len(bucket) >= limit:
                raise AppError(
                    "Too many requests. Please try again later.",
                    status_code=429,
                )
            bucket.append(now)


rate_limiter = InMemoryRateLimiter()


def client_key(request: Request, *, prefix: str) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    else:
        ip = request.client.host if request.client else "unknown"
    return f"{prefix}:{ip}"


def enforce_login_rate_limit(request: Request) -> None:
    rate_limiter.check(
        client_key(request, prefix="login"),
        limit=settings.RATE_LIMIT_LOGIN_PER_MINUTE,
        window_seconds=60,
    )


def enforce_upload_rate_limit(request: Request) -> None:
    rate_limiter.check(
        client_key(request, prefix="upload"),
        limit=settings.RATE_LIMIT_UPLOAD_PER_MINUTE,
        window_seconds=60,
    )


def enforce_ai_rate_limit(request: Request) -> None:
    rate_limiter.check(
        client_key(request, prefix="ai"),
        limit=settings.RATE_LIMIT_AI_PER_MINUTE,
        window_seconds=60,
    )
