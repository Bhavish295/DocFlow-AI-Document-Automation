from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core.request_context import get_request_id


class AppError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _error_headers() -> dict[str, str]:
    request_id = get_request_id()
    if request_id:
        return {"X-Request-ID": request_id}
    return {}


def _safe_detail(message: str, *, status_code: int, exc: BaseException | None = None) -> str:
    if settings.is_development and settings.DEBUG and exc is not None and status_code >= 500:
        return f"{message} ({exc.__class__.__name__}: {exc})"
    return message


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message},
            headers=_error_headers(),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail
        if not isinstance(detail, str):
            detail = "Request failed."
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": detail},
            headers=_error_headers(),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Keep FastAPI-style detail for API clients; never include body secrets.
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": exc.errors()},
            headers=_error_headers(),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
        detail = _safe_detail(
            "An unexpected error occurred.",
            status_code=500,
            exc=exc,
        )
        return JSONResponse(
            status_code=500,
            content={"detail": detail},
            headers=_error_headers(),
        )
