"""Login failure cooldown (in-process, single-instance)."""

from __future__ import annotations

from collections import defaultdict, deque
import threading
import time
from typing import Deque

from app.core.config import settings
from app.core.exceptions import AppError


class LoginFailureTracker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._failures: dict[str, Deque[float]] = defaultdict(deque)

    def reset(self) -> None:
        with self._lock:
            self._failures.clear()

    def _key(self, identifier: str) -> str:
        return (identifier or "").strip().lower()[:200]

    def assert_not_locked(self, identifier: str) -> None:
        max_failures = settings.AUTH_LOGIN_MAX_FAILURES
        window = settings.AUTH_LOGIN_LOCKOUT_SECONDS
        if max_failures <= 0 or window <= 0:
            return
        key = self._key(identifier)
        now = time.monotonic()
        with self._lock:
            bucket = self._failures[key]
            while bucket and now - bucket[0] > window:
                bucket.popleft()
            if len(bucket) >= max_failures:
                raise AppError(
                    "Too many failed login attempts. Please try again later.",
                    status_code=429,
                )

    def record_failure(self, identifier: str) -> None:
        max_failures = settings.AUTH_LOGIN_MAX_FAILURES
        window = settings.AUTH_LOGIN_LOCKOUT_SECONDS
        if max_failures <= 0 or window <= 0:
            return
        key = self._key(identifier)
        now = time.monotonic()
        with self._lock:
            bucket = self._failures[key]
            while bucket and now - bucket[0] > window:
                bucket.popleft()
            bucket.append(now)

    def clear(self, identifier: str) -> None:
        key = self._key(identifier)
        with self._lock:
            self._failures.pop(key, None)


login_failure_tracker = LoginFailureTracker()
