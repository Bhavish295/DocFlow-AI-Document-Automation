from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.schemas.health import HealthResponse, ReadinessResponse

APP_VERSION = "0.1.0"


def get_health_status() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=settings.APP_NAME,
        version=APP_VERSION,
    )


def get_readiness_status(db: Session) -> ReadinessResponse:
    """Verify required runtime dependencies without exposing connection details."""
    checks: dict[str, str] = {}
    overall = "ok"

    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "unavailable"
        overall = "unavailable"

    try:
        upload_dir = settings.upload_dir_path
        upload_dir.mkdir(parents=True, exist_ok=True)
        if upload_dir.is_dir():
            checks["storage"] = "ok"
        else:
            checks["storage"] = "unavailable"
            overall = "unavailable"
    except Exception:
        checks["storage"] = "unavailable"
        overall = "unavailable"

    return ReadinessResponse(
        status=overall,
        service=settings.APP_NAME,
        version=APP_VERSION,
        checks=checks,
    )
