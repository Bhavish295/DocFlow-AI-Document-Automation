"""Read-only analytics aggregations for management reporting (Step 24)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from statistics import median
from typing import Any

from sqlalchemy import cast, func, select
from sqlalchemy.orm import Session
from sqlalchemy.types import Date

from app.models.anomaly import AnomalyStatus, DocumentAnomaly
from app.models.document import Document, DocumentStatus
from app.models.document_processing_job import ACTIVE_JOB_STATUSES, DocumentProcessingJob, ProcessingJobStatus
from app.models.document_review import ACTIVE_REVIEW_STATUSES, DocumentReview, ReviewStatus
from app.models.duplicate import DocumentDuplicate, DuplicateDetectionType, DuplicateStatus
from app.models.goods_receipt import GoodsReceipt
from app.models.invoice import Invoice
from app.models.purchase_order import PurchaseOrder
from app.models.three_way_match import ThreeWayMatch
from app.models.validation import DocumentValidation, ValidationStatus
from app.models.vendor import Vendor
from app.schemas.analytics import (
    AnalyticsSummaryResponse,
    AnomalyAnalyticsResponse,
    CurrencyTotals,
    DocumentAnalyticsResponse,
    DuplicateAnalyticsResponse,
    InvoiceAnalyticsResponse,
    NamedCount,
    ProcessingAnalyticsResponse,
    ReviewAnalyticsResponse,
    TrendSeriesPoint,
    TrendsAnalyticsResponse,
    ValidationAnalyticsResponse,
    VendorAnalyticsResponse,
    VendorAnalyticsRow,
)


def _f(value: Any) -> float:
    if value is None:
        return 0.0
    return float(value)


def _i(value: Any) -> int:
    if value is None:
        return 0
    return int(value)


def _counts_map(rows: list[tuple[Any, Any]]) -> dict[str, int]:
    return {str(name if name is not None else "unknown"): _i(count) for name, count in rows}


def _named_counts(rows: list[tuple[Any, Any]]) -> list[NamedCount]:
    return [NamedCount(name=str(name if name is not None else "unknown"), count=_i(count)) for name, count in rows]


class AnalyticsService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def summary(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        document_type: str | None = None,
    ) -> AnalyticsSummaryResponse:
        doc_filters = self._document_filters(date_from, date_to, document_type)

        total_documents = self._count(select(func.count()).select_from(Document).where(*doc_filters))
        processed_documents = self._count(
            select(func.count()).select_from(Document).where(
                *doc_filters, Document.status == DocumentStatus.PROCESSED.value
            )
        )
        failed_documents = self._count(
            select(func.count()).select_from(Document).where(
                *doc_filters, Document.status == DocumentStatus.FAILED.value
            )
        )
        documents_requiring_review = self._count(
            select(func.count()).select_from(DocumentReview).where(
                DocumentReview.status.in_(tuple(ACTIVE_REVIEW_STATUSES))
            )
        )

        inv_filters = self._invoice_date_filters(date_from, date_to)
        total_invoices = self._count(select(func.count()).select_from(Invoice).where(*inv_filters))
        by_currency = self._invoice_currency_totals(inv_filters)

        total_purchase_orders = self._count(select(func.count()).select_from(PurchaseOrder))
        total_goods_receipts = self._count(select(func.count()).select_from(GoodsReceipt))

        validation_counts = _counts_map(
            list(
                self.db.execute(
                    select(DocumentValidation.status, func.count())
                    .group_by(DocumentValidation.status)
                ).all()
            )
        )
        three_way_counts = _counts_map(
            list(
                self.db.execute(
                    select(ThreeWayMatch.status, func.count()).group_by(ThreeWayMatch.status)
                ).all()
            )
        )

        duplicate_pending = self._count(
            select(func.count()).select_from(DocumentDuplicate).where(
                DocumentDuplicate.status == DuplicateStatus.PENDING.value
            )
        )
        anomaly_count = self._count(
            select(func.count()).select_from(DocumentAnomaly).where(
                DocumentAnomaly.status.in_(
                    (
                        AnomalyStatus.ANOMALY.value,
                        AnomalyStatus.REQUIRES_REVIEW.value,
                        AnomalyStatus.UNUSUAL.value,
                    )
                )
            )
        )
        active_processing_jobs = self._count(
            select(func.count()).select_from(DocumentProcessingJob).where(
                DocumentProcessingJob.status.in_(ACTIVE_JOB_STATUSES)
            )
        )

        return AnalyticsSummaryResponse(
            total_documents=total_documents,
            processed_documents=processed_documents,
            failed_documents=failed_documents,
            documents_requiring_review=documents_requiring_review,
            total_invoices=total_invoices,
            total_invoice_value_by_currency=by_currency,
            total_purchase_orders=total_purchase_orders,
            total_goods_receipts=total_goods_receipts,
            validation_matched=validation_counts.get(ValidationStatus.MATCHED.value, 0),
            validation_mismatch=validation_counts.get(ValidationStatus.MISMATCH.value, 0),
            validation_needs_review=validation_counts.get(ValidationStatus.NEEDS_REVIEW.value, 0),
            three_way_matched=three_way_counts.get("matched", 0),
            three_way_mismatch=three_way_counts.get("mismatch", 0),
            three_way_needs_review=three_way_counts.get("needs_review", 0),
            duplicate_pending=duplicate_pending,
            anomaly_count=anomaly_count,
            active_processing_jobs=active_processing_jobs,
        )

    def documents(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        document_type: str | None = None,
        status: str | None = None,
    ) -> DocumentAnalyticsResponse:
        filters = self._document_filters(date_from, date_to, document_type)
        if status:
            filters.append(Document.status == status)

        by_type = _named_counts(
            list(
                self.db.execute(
                    select(Document.document_type, func.count())
                    .where(*filters)
                    .group_by(Document.document_type)
                    .order_by(func.count().desc())
                ).all()
            )
        )
        by_status = _named_counts(
            list(
                self.db.execute(
                    select(Document.status, func.count())
                    .where(*filters)
                    .group_by(Document.status)
                    .order_by(func.count().desc())
                ).all()
            )
        )
        status_map = {item.name: item.count for item in by_status}
        processing = {
            "processed": status_map.get(DocumentStatus.PROCESSED.value, 0),
            "failed": status_map.get(DocumentStatus.FAILED.value, 0),
            "processing": status_map.get(DocumentStatus.PROCESSING.value, 0),
            "uploaded": status_map.get(DocumentStatus.UPLOADED.value, 0),
            "manual_review": status_map.get(DocumentStatus.MANUAL_REVIEW.value, 0),
        }
        review_required = self._count(
            select(func.count()).select_from(DocumentReview).where(
                DocumentReview.status.in_(tuple(ACTIVE_REVIEW_STATUSES))
            )
        )
        return DocumentAnalyticsResponse(
            by_type=by_type,
            by_status=by_status,
            processing=processing,
            review_required=review_required,
        )

    def invoices(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        currency: str | None = None,
    ) -> InvoiceAnalyticsResponse:
        filters = self._invoice_date_filters(date_from, date_to)
        if currency:
            filters.append(func.upper(Invoice.currency) == currency.upper())
        invoice_count = self._count(select(func.count()).select_from(Invoice).where(*filters))
        return InvoiceAnalyticsResponse(
            invoice_count=invoice_count,
            by_currency=self._invoice_currency_totals(filters),
        )

    def vendors(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        currency: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> VendorAnalyticsResponse:
        page = max(1, page)
        page_size = min(100, max(1, page_size))
        filters = self._invoice_date_filters(date_from, date_to)
        if currency:
            filters.append(func.upper(Invoice.currency) == currency.upper())

        vendor_label = func.coalesce(Vendor.name, Invoice.vendor_name, "Unknown")
        currency_expr = func.coalesce(func.upper(Invoice.currency), "UNKNOWN")

        base = (
            select(
                vendor_label.label("vendor"),
                Vendor.id.label("vendor_id"),
                currency_expr.label("currency"),
                func.count(Invoice.id).label("invoice_count"),
                func.coalesce(func.sum(Invoice.total_amount), 0).label("total_value"),
                func.coalesce(func.avg(Invoice.total_amount), 0).label("average_invoice"),
            )
            .select_from(Invoice)
            .outerjoin(Vendor, Vendor.id == Invoice.vendor_id)
            .where(*filters)
            .group_by(vendor_label, Vendor.id, currency_expr)
        )

        count_subq = base.subquery()
        total = self._count(select(func.count()).select_from(count_subq))
        vendor_count = self._count(select(func.count(func.distinct(Vendor.id))).select_from(Vendor))

        rows = list(
            self.db.execute(
                base.order_by(func.count(Invoice.id).desc(), vendor_label.asc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )

        items: list[VendorAnalyticsRow] = []
        for row in rows:
            vendor_name = str(row.vendor or "Unknown")
            currency_code = str(row.currency or "UNKNOWN")
            validation_issues = self._vendor_validation_issues(vendor_name)
            review_count = self._vendor_review_count(vendor_name)
            items.append(
                VendorAnalyticsRow(
                    vendor=vendor_name,
                    vendor_id=str(row.vendor_id) if row.vendor_id else None,
                    invoice_count=_i(row.invoice_count),
                    total_value=round(_f(row.total_value), 2),
                    currency=currency_code,
                    average_invoice=round(_f(row.average_invoice), 2),
                    validation_issues=validation_issues,
                    review_count=review_count,
                )
            )

        return VendorAnalyticsResponse(
            vendor_count=vendor_count,
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )

    def reviews(self) -> ReviewAnalyticsResponse:
        status_counts = _counts_map(
            list(
                self.db.execute(
                    select(DocumentReview.status, func.count()).group_by(DocumentReview.status)
                ).all()
            )
        )
        by_reason = _named_counts(
            list(
                self.db.execute(
                    select(DocumentReview.reason, func.count())
                    .group_by(DocumentReview.reason)
                    .order_by(func.count().desc())
                ).all()
            )
        )
        avg_hours, med_hours = self._review_age_hours()
        total = sum(status_counts.values())
        return ReviewAnalyticsResponse(
            pending=status_counts.get(ReviewStatus.PENDING.value, 0),
            in_review=status_counts.get(ReviewStatus.IN_REVIEW.value, 0),
            approved=status_counts.get(ReviewStatus.APPROVED.value, 0),
            rejected=status_counts.get(ReviewStatus.REJECTED.value, 0),
            total=total,
            by_reason=by_reason,
            average_age_hours=avg_hours,
            median_age_hours=med_hours,
        )

    def validations(self) -> ValidationAnalyticsResponse:
        invoice_po = {
            "matched": 0,
            "mismatch": 0,
            "needs_review": 0,
        }
        invoice_po.update(
            _counts_map(
                list(
                    self.db.execute(
                        select(DocumentValidation.status, func.count()).group_by(DocumentValidation.status)
                    ).all()
                )
            )
        )
        three_way = {
            "matched": 0,
            "mismatch": 0,
            "needs_review": 0,
        }
        three_way.update(
            _counts_map(
                list(
                    self.db.execute(
                        select(ThreeWayMatch.status, func.count()).group_by(ThreeWayMatch.status)
                    ).all()
                )
            )
        )

        dimensions: list[NamedCount] = []
        for label, column in (
            ("vendor", DocumentValidation.vendor_match),
            ("currency", DocumentValidation.currency_match),
            ("subtotal", DocumentValidation.subtotal_match),
            ("tax", DocumentValidation.tax_match),
            ("total", DocumentValidation.total_match),
        ):
            count = self._count(
                select(func.count()).select_from(DocumentValidation).where(column.is_(False))
            )
            if count:
                dimensions.append(NamedCount(name=label, count=count))

        return ValidationAnalyticsResponse(
            invoice_po=invoice_po,
            three_way=three_way,
            mismatch_dimensions=dimensions,
        )

    def anomalies(self) -> AnomalyAnalyticsResponse:
        counts = _counts_map(
            list(
                self.db.execute(
                    select(DocumentAnomaly.status, func.count()).group_by(DocumentAnomaly.status)
                ).all()
            )
        )
        return AnomalyAnalyticsResponse(
            normal=counts.get(AnomalyStatus.NORMAL.value, 0),
            unusual=counts.get(AnomalyStatus.UNUSUAL.value, 0),
            anomaly=counts.get(AnomalyStatus.ANOMALY.value, 0),
            requires_review=counts.get(AnomalyStatus.REQUIRES_REVIEW.value, 0),
            total_scored=sum(counts.values()),
        )

    def duplicates(self) -> DuplicateAnalyticsResponse:
        type_counts = _counts_map(
            list(
                self.db.execute(
                    select(DocumentDuplicate.detection_type, func.count()).group_by(
                        DocumentDuplicate.detection_type
                    )
                ).all()
            )
        )
        status_counts = _counts_map(
            list(
                self.db.execute(
                    select(DocumentDuplicate.status, func.count()).group_by(DocumentDuplicate.status)
                ).all()
            )
        )
        return DuplicateAnalyticsResponse(
            exact_duplicate=type_counts.get(DuplicateDetectionType.EXACT_DUPLICATE.value, 0),
            business_duplicate=type_counts.get(DuplicateDetectionType.BUSINESS_DUPLICATE.value, 0),
            similar_duplicate=type_counts.get(DuplicateDetectionType.SIMILAR_DUPLICATE.value, 0),
            pending=status_counts.get(DuplicateStatus.PENDING.value, 0),
            confirmed=status_counts.get(DuplicateStatus.CONFIRMED.value, 0),
            dismissed=status_counts.get(DuplicateStatus.DISMISSED.value, 0),
        )

    def processing(self) -> ProcessingAnalyticsResponse:
        counts = _counts_map(
            list(
                self.db.execute(
                    select(DocumentProcessingJob.status, func.count()).group_by(
                        DocumentProcessingJob.status
                    )
                ).all()
            )
        )
        avg_seconds, sample_count = self._average_processing_duration()
        return ProcessingAnalyticsResponse(
            queued=counts.get(ProcessingJobStatus.QUEUED.value, 0),
            running=counts.get(ProcessingJobStatus.RUNNING.value, 0),
            completed=counts.get(ProcessingJobStatus.COMPLETED.value, 0),
            failed=counts.get(ProcessingJobStatus.FAILED.value, 0),
            cancelled=counts.get(ProcessingJobStatus.CANCELLED.value, 0),
            average_duration_seconds=avg_seconds,
            duration_sample_count=sample_count,
        )

    def trends(
        self,
        *,
        period: str = "30d",
        document_type: str | None = None,
    ) -> TrendsAnalyticsResponse:
        period_key = (period or "30d").lower()
        if period_key not in {"7d", "30d", "90d", "12m"}:
            period_key = "30d"

        now = datetime.now(timezone.utc)
        if period_key == "7d":
            start = now - timedelta(days=7)
            granularity = "day"
        elif period_key == "30d":
            start = now - timedelta(days=30)
            granularity = "day"
        elif period_key == "90d":
            start = now - timedelta(days=90)
            granularity = "day"
        else:
            start = now - timedelta(days=365)
            granularity = "month"

        buckets = self._build_buckets(start, now, granularity)
        point_map = {
            key: TrendSeriesPoint(period=key)
            for key in buckets
        }

        doc_filters = [Document.uploaded_at >= start]
        if document_type:
            doc_filters.append(Document.document_type == document_type)

        uploaded_rows = self.db.execute(
            select(cast(Document.uploaded_at, Date), func.count())
            .where(*doc_filters)
            .group_by(cast(Document.uploaded_at, Date))
        ).all()
        for day, count in uploaded_rows:
            key = self._bucket_key(day, granularity)
            if key in point_map:
                point_map[key].uploaded_documents += _i(count)

        processed_rows = self.db.execute(
            select(cast(Document.processed_at, Date), func.count())
            .where(
                Document.processed_at.is_not(None),
                Document.processed_at >= start,
                Document.status == DocumentStatus.PROCESSED.value,
                *([Document.document_type == document_type] if document_type else []),
            )
            .group_by(cast(Document.processed_at, Date))
        ).all()
        for day, count in processed_rows:
            key = self._bucket_key(day, granularity)
            if key in point_map:
                point_map[key].processed_documents += _i(count)

        invoice_rows = self.db.execute(
            select(cast(Invoice.created_at, Date), func.count())
            .where(Invoice.created_at >= start)
            .group_by(cast(Invoice.created_at, Date))
        ).all()
        for day, count in invoice_rows:
            key = self._bucket_key(day, granularity)
            if key in point_map:
                point_map[key].invoices += _i(count)

        review_rows = self.db.execute(
            select(cast(DocumentReview.created_at, Date), func.count())
            .where(DocumentReview.created_at >= start)
            .group_by(cast(DocumentReview.created_at, Date))
        ).all()
        for day, count in review_rows:
            key = self._bucket_key(day, granularity)
            if key in point_map:
                point_map[key].review_items += _i(count)

        mismatch_rows = self.db.execute(
            select(cast(DocumentValidation.created_at, Date), func.count())
            .where(
                DocumentValidation.created_at >= start,
                DocumentValidation.status == ValidationStatus.MISMATCH.value,
            )
            .group_by(cast(DocumentValidation.created_at, Date))
        ).all()
        for day, count in mismatch_rows:
            key = self._bucket_key(day, granularity)
            if key in point_map:
                point_map[key].validation_mismatches += _i(count)

        anomaly_rows = self.db.execute(
            select(cast(DocumentAnomaly.detected_at, Date), func.count())
            .where(
                DocumentAnomaly.detected_at >= start,
                DocumentAnomaly.status.in_(
                    (
                        AnomalyStatus.ANOMALY.value,
                        AnomalyStatus.REQUIRES_REVIEW.value,
                        AnomalyStatus.UNUSUAL.value,
                    )
                ),
            )
            .group_by(cast(DocumentAnomaly.detected_at, Date))
        ).all()
        for day, count in anomaly_rows:
            key = self._bucket_key(day, granularity)
            if key in point_map:
                point_map[key].anomaly_findings += _i(count)

        return TrendsAnalyticsResponse(
            period=period_key,
            granularity=granularity,
            points=[point_map[key] for key in buckets],
        )

    def _count(self, statement) -> int:
        return _i(self.db.scalar(statement) or 0)

    def _document_filters(
        self,
        date_from: date | None,
        date_to: date | None,
        document_type: str | None,
    ) -> list:
        filters: list = []
        if date_from:
            filters.append(
                Document.uploaded_at
                >= datetime.combine(date_from, datetime.min.time(), tzinfo=timezone.utc)
            )
        if date_to:
            filters.append(
                Document.uploaded_at
                <= datetime.combine(date_to, datetime.max.time(), tzinfo=timezone.utc)
            )
        if document_type:
            filters.append(Document.document_type == document_type)
        return filters

    def _invoice_date_filters(self, date_from: date | None, date_to: date | None) -> list:
        filters: list = []
        if date_from:
            filters.append(
                Invoice.created_at
                >= datetime.combine(date_from, datetime.min.time(), tzinfo=timezone.utc)
            )
        if date_to:
            filters.append(
                Invoice.created_at
                <= datetime.combine(date_to, datetime.max.time(), tzinfo=timezone.utc)
            )
        return filters

    def _invoice_currency_totals(self, filters: list) -> list[CurrencyTotals]:
        currency_expr = func.coalesce(func.upper(Invoice.currency), "UNKNOWN")
        rows = self.db.execute(
            select(
                currency_expr.label("currency"),
                func.count(Invoice.id),
                func.coalesce(func.sum(Invoice.total_amount), 0),
                func.coalesce(func.avg(Invoice.total_amount), 0),
                func.min(Invoice.total_amount),
                func.max(Invoice.total_amount),
                func.coalesce(func.sum(Invoice.tax_amount), 0),
                func.coalesce(func.avg(Invoice.tax_amount), 0),
            )
            .where(*filters)
            .group_by(currency_expr)
            .order_by(currency_expr.asc())
        ).all()
        return [
            CurrencyTotals(
                currency=str(row[0] or "UNKNOWN"),
                count=_i(row[1]),
                total=round(_f(row[2]), 2),
                average=round(_f(row[3]), 2),
                minimum=None if row[4] is None else round(_f(row[4]), 2),
                maximum=None if row[5] is None else round(_f(row[5]), 2),
                total_tax=round(_f(row[6]), 2),
                average_tax=round(_f(row[7]), 2),
            )
            for row in rows
        ]

    def _vendor_validation_issues(self, vendor_name: str) -> int:
        return self._count(
            select(func.count())
            .select_from(DocumentValidation)
            .join(Invoice, Invoice.id == DocumentValidation.invoice_id)
            .where(
                DocumentValidation.status.in_(
                    (ValidationStatus.MISMATCH.value, ValidationStatus.NEEDS_REVIEW.value)
                ),
                Invoice.vendor_name == vendor_name,
            )
        )

    def _vendor_review_count(self, vendor_name: str) -> int:
        return self._count(
            select(func.count())
            .select_from(DocumentReview)
            .join(Invoice, Invoice.document_id == DocumentReview.document_id)
            .where(Invoice.vendor_name == vendor_name)
        )

    def _review_age_hours(self) -> tuple[float | None, float | None]:
        now = datetime.now(timezone.utc)
        created_ats = list(
            self.db.scalars(
                select(DocumentReview.created_at).where(
                    DocumentReview.status.in_(tuple(ACTIVE_REVIEW_STATUSES))
                )
            ).all()
        )
        if not created_ats:
            return None, None
        ages = []
        for created in created_ats:
            if created is None:
                continue
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            ages.append(max(0.0, (now - created).total_seconds() / 3600.0))
        if not ages:
            return None, None
        return round(sum(ages) / len(ages), 2), round(float(median(ages)), 2)

    def _average_processing_duration(self) -> tuple[float | None, int]:
        rows = self.db.execute(
            select(DocumentProcessingJob.started_at, DocumentProcessingJob.completed_at).where(
                DocumentProcessingJob.started_at.is_not(None),
                DocumentProcessingJob.completed_at.is_not(None),
                DocumentProcessingJob.status == ProcessingJobStatus.COMPLETED.value,
            )
        ).all()
        durations: list[float] = []
        for started, completed in rows:
            if started is None or completed is None:
                continue
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            if completed.tzinfo is None:
                completed = completed.replace(tzinfo=timezone.utc)
            seconds = (completed - started).total_seconds()
            if seconds >= 0:
                durations.append(seconds)
        if not durations:
            return None, 0
        return round(sum(durations) / len(durations), 2), len(durations)

    def _build_buckets(self, start: datetime, end: datetime, granularity: str) -> list[str]:
        buckets: list[str] = []
        if granularity == "month":
            cursor = date(start.year, start.month, 1)
            end_month = date(end.year, end.month, 1)
            while cursor <= end_month:
                buckets.append(f"{cursor.year:04d}-{cursor.month:02d}")
                if cursor.month == 12:
                    cursor = date(cursor.year + 1, 1, 1)
                else:
                    cursor = date(cursor.year, cursor.month + 1, 1)
            return buckets

        cursor = start.date()
        end_day = end.date()
        while cursor <= end_day:
            buckets.append(cursor.isoformat())
            cursor += timedelta(days=1)
        return buckets

    def _bucket_key(self, value: date | datetime | None, granularity: str) -> str:
        if value is None:
            return ""
        if isinstance(value, datetime):
            value = value.date()
        if granularity == "month":
            return f"{value.year:04d}-{value.month:02d}"
        return value.isoformat()
