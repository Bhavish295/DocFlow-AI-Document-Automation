"""Read-only analytics API routes (Step 24)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.user import User
from app.schemas.analytics import (
    AnalyticsSummaryResponse,
    AnomalyAnalyticsResponse,
    DocumentAnalyticsResponse,
    DuplicateAnalyticsResponse,
    InvoiceAnalyticsResponse,
    ProcessingAnalyticsResponse,
    ReviewAnalyticsResponse,
    TrendsAnalyticsResponse,
    ValidationAnalyticsResponse,
    VendorAnalyticsResponse,
)
from app.services.analytics import AnalyticsService


router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/summary", response_model=AnalyticsSummaryResponse)
def analytics_summary(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    document_type: str | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.ANALYTICS_READ)),
) -> AnalyticsSummaryResponse:
    return AnalyticsService(db).summary(
        date_from=date_from,
        date_to=date_to,
        document_type=document_type,
    )


@router.get("/documents", response_model=DocumentAnalyticsResponse)
def analytics_documents(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    document_type: str | None = Query(None),
    status: str | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.ANALYTICS_READ)),
) -> DocumentAnalyticsResponse:
    return AnalyticsService(db).documents(
        date_from=date_from,
        date_to=date_to,
        document_type=document_type,
        status=status,
    )


@router.get("/invoices", response_model=InvoiceAnalyticsResponse)
def analytics_invoices(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    currency: str | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.ANALYTICS_READ)),
) -> InvoiceAnalyticsResponse:
    return AnalyticsService(db).invoices(
        date_from=date_from,
        date_to=date_to,
        currency=currency,
    )


@router.get("/vendors", response_model=VendorAnalyticsResponse)
def analytics_vendors(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    currency: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.ANALYTICS_READ)),
) -> VendorAnalyticsResponse:
    return AnalyticsService(db).vendors(
        page=page,
        page_size=page_size,
        currency=currency,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/reviews", response_model=ReviewAnalyticsResponse)
def analytics_reviews(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.ANALYTICS_READ)),
) -> ReviewAnalyticsResponse:
    return AnalyticsService(db).reviews()


@router.get("/validations", response_model=ValidationAnalyticsResponse)
def analytics_validations(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.ANALYTICS_READ)),
) -> ValidationAnalyticsResponse:
    return AnalyticsService(db).validations()


@router.get("/anomalies", response_model=AnomalyAnalyticsResponse)
def analytics_anomalies(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.ANALYTICS_READ)),
) -> AnomalyAnalyticsResponse:
    return AnalyticsService(db).anomalies()


@router.get("/duplicates", response_model=DuplicateAnalyticsResponse)
def analytics_duplicates(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.ANALYTICS_READ)),
) -> DuplicateAnalyticsResponse:
    return AnalyticsService(db).duplicates()


@router.get("/processing", response_model=ProcessingAnalyticsResponse)
def analytics_processing(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.ANALYTICS_READ)),
) -> ProcessingAnalyticsResponse:
    return AnalyticsService(db).processing()


@router.get("/trends", response_model=TrendsAnalyticsResponse)
def analytics_trends(
    period: str = Query("30d", pattern="^(7d|30d|90d|12m)$"),
    document_type: str | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.ANALYTICS_READ)),
) -> TrendsAnalyticsResponse:
    return AnalyticsService(db).trends(period=period, document_type=document_type)
