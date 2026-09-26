from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.health import HealthResponse, ReadinessResponse
from app.services.health import get_health_status, get_readiness_status


router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return get_health_status()


@router.get("/health/ready", response_model=ReadinessResponse)
def readiness_check(response: Response, db: Session = Depends(get_db)) -> ReadinessResponse:
    payload = get_readiness_status(db)
    if payload.status != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return payload
