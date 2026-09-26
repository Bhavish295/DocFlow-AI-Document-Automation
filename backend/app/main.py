from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings, validate_production_settings
from app.core.database import SessionLocal
from app.core.exceptions import register_exception_handlers
from app.core.logging_config import configure_logging
from app.core.middleware import RequestContextMiddleware, SecurityHeadersMiddleware
from app.services.bootstrap import bootstrap_admin_user


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_application: FastAPI):
    configure_logging()
    problems = validate_production_settings(settings)
    if problems:
        message = "; ".join(problems)
        logger.error("Production configuration invalid: %s", message)
        raise RuntimeError(f"Production configuration invalid: {message}")

    try:
        db = SessionLocal()
        try:
            bootstrap_admin_user(db)
        finally:
            db.close()
    except Exception:
        # Tests / misconfigured DBs should not prevent the API from starting.
        logger.warning("Bootstrap admin skipped due to database error", exc_info=settings.DEBUG)
    yield


def create_app() -> FastAPI:
    docs_url = "/docs" if settings.docs_enabled else None
    redoc_url = "/redoc" if settings.docs_enabled else None
    openapi_url = "/openapi.json" if settings.docs_enabled else None

    application = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
        lifespan=lifespan,
    )

    origins = settings.cors_origin_list
    if settings.is_production and ("*" in origins or not origins):
        raise RuntimeError(
            "CORS_ORIGINS must be an explicit allow-list in production "
            "(wildcard '*' is not permitted with credentials)."
        )

    # Middleware order: last added runs first on the request.
    application.add_middleware(SecurityHeadersMiddleware)
    application.add_middleware(RequestContextMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    register_exception_handlers(application)
    application.include_router(api_router, prefix=settings.API_V1_PREFIX)

    return application


app = create_app()
