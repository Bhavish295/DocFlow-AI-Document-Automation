"""ASGI middleware: security headers, request IDs, body size guard, access logging."""

from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.core.request_context import reset_request_id, set_request_id

logger = logging.getLogger("app.access")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Referrer-Policy", "strict-origin-when-cross-origin"
        )
        if settings.hsts_enabled:
            response.headers.setdefault(
                "Strict-Transport-Security",
                f"max-age={settings.HSTS_MAX_AGE_SECONDS}; includeSubDomains",
            )
        return response


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        incoming = request.headers.get("x-request-id") or request.headers.get(
            "x-correlation-id"
        )
        request_id = (incoming or "").strip() or str(uuid.uuid4())
        token = set_request_id(request_id)
        request.state.request_id = request_id
        started = time.perf_counter()
        try:
            # Reject oversized bodies early when Content-Length is present
            max_bytes = settings.max_request_body_bytes
            content_length = request.headers.get("content-length")
            if content_length is not None:
                try:
                    length = int(content_length)
                except ValueError:
                    length = -1
                if length > max_bytes:
                    return JSONResponse(
                        status_code=413,
                        content={"detail": "Request body is too large."},
                        headers={"X-Request-ID": request_id},
                    )

            response = await call_next(request)
        except Exception:
            duration_ms = int((time.perf_counter() - started) * 1000)
            logger.exception(
                "unhandled_error method=%s path=%s duration_ms=%s request_id=%s",
                request.method,
                request.url.path,
                duration_ms,
                request_id,
            )
            raise
        else:
            duration_ms = int((time.perf_counter() - started) * 1000)
            user_id = getattr(request.state, "user_id", None)
            logger.info(
                "request method=%s path=%s status=%s duration_ms=%s request_id=%s user_id=%s",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
                request_id,
                user_id or "-",
            )
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            reset_request_id(token)
