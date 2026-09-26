from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.user import User
from app.schemas.anomaly import (
    AnomalyListResponse,
    AnomalyModelRunListResponse,
    AnomalyModelRunResponse,
    AnomalyResult,
    AnomalyScoreBatchResponse,
    AnomalyScoreRequest,
    AnomalySummaryResponse,
    AnomalyTrainRequest,
)
from app.services.anomaly_service import AnomalyService


router = APIRouter()


@router.post("/anomalies/train", response_model=AnomalyModelRunResponse)
def train_anomaly_model(
    payload: AnomalyTrainRequest | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.ANOMALIES_TRAIN)),
) -> AnomalyModelRunResponse:
    body = payload or AnomalyTrainRequest()
    result = AnomalyService(db).train(
        contamination=body.contamination,
        min_samples=body.min_samples,
    )
    return AnomalyModelRunResponse(**result)


@router.post("/anomalies/score", response_model=AnomalyResult | AnomalyScoreBatchResponse)
def score_anomalies(
    payload: AnomalyScoreRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.ANOMALIES_SCORE)),
) -> AnomalyResult | AnomalyScoreBatchResponse:
    service = AnomalyService(db)
    if payload.document_id is not None:
        result = service.score_document(payload.document_id, force=payload.force)
        return AnomalyResult(**result)

    document_ids = payload.document_ids
    result = service.score_many(
        document_ids,
        force=payload.force,
        limit=payload.limit,
    )
    return AnomalyScoreBatchResponse(**result)


@router.get("/anomalies", response_model=AnomalyListResponse)
def list_anomalies(
    status: str | None = None,
    min_score: float | None = Query(default=None, ge=0.0, le=1.0),
    vendor: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = "detected_at",
    sort_order: str = "desc",
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.ANOMALIES_READ)),
) -> AnomalyListResponse:
    payload = AnomalyService(db).list_anomalies(
        status=status,
        min_score=min_score,
        vendor=vendor,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return AnomalyListResponse(**payload)


@router.get("/anomalies/summary", response_model=AnomalySummaryResponse)
def anomaly_summary(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.ANOMALIES_READ)),
) -> AnomalySummaryResponse:
    return AnomalySummaryResponse(**AnomalyService(db).summary())


@router.get("/anomalies/{document_id}", response_model=AnomalyResult)
def get_document_anomaly(
    document_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.ANOMALIES_READ)),
) -> AnomalyResult:
    return AnomalyResult(**AnomalyService(db).get_anomaly_for_document(document_id))


@router.get("/anomaly-model-runs", response_model=AnomalyModelRunListResponse)
def list_anomaly_model_runs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.ANOMALIES_READ)),
) -> AnomalyModelRunListResponse:
    payload = AnomalyService(db).list_model_runs(page=page, page_size=page_size)
    return AnomalyModelRunListResponse(**payload)
