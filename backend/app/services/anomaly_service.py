"""Anomaly detection orchestration: train, score, persist, explain."""

from __future__ import annotations

from datetime import datetime, timezone
from math import ceil
from typing import Any
import uuid

from sqlalchemy import asc, desc, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppError
from app.models.anomaly import AnomalyModelRun, AnomalyModelRunStatus, DocumentAnomaly
from app.models.document import Document
from app.models.invoice import Invoice
from app.services.anomaly_features import (
    FEATURE_NAMES,
    build_feature_matrix,
    build_feature_row_for_invoice,
    explain_feature_deviations,
)
from app.services.anomaly_model import (
    load_trained_model,
    save_trained_model,
    score_vector,
    train_isolation_forest,
)


class AnomalyService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def train(
        self,
        *,
        contamination: float | None = None,
        min_samples: int | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        run = AnomalyModelRun(
            model_name=settings.ANOMALY_MODEL_NAME,
            model_version=settings.ANOMALY_MODEL_VERSION,
            status=AnomalyModelRunStatus.TRAINING.value,
            trained_at=None,
            sample_count=0,
            feature_count=len(FEATURE_NAMES),
            model_metadata={"feature_names": list(FEATURE_NAMES)},
            created_at=now,
        )
        self.db.add(run)
        self.db.flush()

        rows = build_feature_matrix(self.db)
        min_required = min_samples if min_samples is not None else settings.ANOMALY_MIN_TRAINING_SAMPLES
        if len(rows) < min_required:
            run.status = AnomalyModelRunStatus.INSUFFICIENT_DATA.value
            run.sample_count = len(rows)
            run.model_metadata = {
                "feature_names": list(FEATURE_NAMES),
                "min_required": min_required,
                "message": (
                    f"Need at least {min_required} invoices with total amounts to train. "
                    f"Found {len(rows)}."
                ),
            }
            self.db.commit()
            self.db.refresh(run)
            return self._run_payload(run)

        try:
            trained = train_isolation_forest(
                [row.vector for row in rows],
                contamination=contamination,
                min_samples=min_required,
            )
            path = save_trained_model(trained, run.id)
            run.status = AnomalyModelRunStatus.READY.value
            run.trained_at = datetime.now(timezone.utc)
            run.sample_count = trained.sample_count
            run.feature_count = len(FEATURE_NAMES)
            run.model_metadata = {
                **trained.to_metadata(),
                "artifact_path": str(path),
                "leakage_policy": (
                    "Vendor historical stats for each invoice use only earlier invoices "
                    "(created_at, then id)."
                ),
                "disclaimer": (
                    "Statistical anomaly scores are not fraud determinations. "
                    "Human review is required for important decisions."
                ),
            }
            self.db.commit()
            self.db.refresh(run)
            return self._run_payload(run)
        except AppError as exc:
            run.status = AnomalyModelRunStatus.FAILED.value
            run.model_metadata = {
                "feature_names": list(FEATURE_NAMES),
                "error": exc.message,
            }
            self.db.commit()
            self.db.refresh(run)
            raise
        except Exception as exc:
            run.status = AnomalyModelRunStatus.FAILED.value
            run.model_metadata = {
                "feature_names": list(FEATURE_NAMES),
                "error": "Model training failed.",
            }
            self.db.commit()
            self.db.refresh(run)
            raise AppError("Anomaly model training failed.", status_code=500) from exc

    def get_latest_ready_run(self) -> AnomalyModelRun | None:
        return self.db.scalar(
            select(AnomalyModelRun)
            .where(AnomalyModelRun.status == AnomalyModelRunStatus.READY.value)
            .order_by(AnomalyModelRun.trained_at.desc(), AnomalyModelRun.created_at.desc())
        )

    def score_document(
        self,
        document_id: uuid.UUID,
        *,
        force: bool = False,
        model_run_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        document = self.db.get(Document, document_id)
        if document is None:
            raise AppError("Document not found.", status_code=404)

        invoice = self.db.scalar(select(Invoice).where(Invoice.document_id == document_id))
        if invoice is None:
            raise AppError("No invoice found for this document.", status_code=400)

        run = None
        if model_run_id is not None:
            run = self.db.get(AnomalyModelRun, model_run_id)
            if run is None:
                raise AppError("Model run not found.", status_code=404)
        else:
            run = self.get_latest_ready_run()
        if run is None or run.status != AnomalyModelRunStatus.READY.value:
            raise AppError(
                "No trained anomaly model is ready. Train the model first.",
                status_code=400,
            )

        existing = self.db.scalar(
            select(DocumentAnomaly).where(
                DocumentAnomaly.document_id == document_id,
                DocumentAnomaly.model_run_id == run.id,
            )
        )
        if existing is not None and not force:
            return self._anomaly_payload(existing, document=document, invoice=invoice, run=run)

        row = build_feature_row_for_invoice(self.db, invoice)
        if row is None:
            raise AppError(
                "Invoice is missing a total amount and cannot be scored.",
                status_code=400,
            )

        artifact = (run.model_metadata or {}).get("artifact_path")
        if not artifact:
            raise AppError("Model artifact is missing for this run.", status_code=500)
        trained = load_trained_model(artifact)
        anomaly_score, status, decision = score_vector(trained, row.vector)
        reasons = explain_feature_deviations(row)

        now = datetime.now(timezone.utc)
        if existing is None:
            existing = DocumentAnomaly(
                document_id=document_id,
                model_run_id=run.id,
                anomaly_score=anomaly_score,
                status=status,
                reasons=reasons,
                feature_values={
                    **row.features,
                    "decision_function": decision,
                    "raw": row.raw_values,
                },
                detected_at=now,
            )
            self.db.add(existing)
        else:
            existing.anomaly_score = anomaly_score
            existing.status = status
            existing.reasons = reasons
            existing.feature_values = {
                **row.features,
                "decision_function": decision,
                "raw": row.raw_values,
            }
            existing.detected_at = now

        self.db.commit()
        self.db.refresh(existing)
        return self._anomaly_payload(existing, document=document, invoice=invoice, run=run)

    def score_many(
        self,
        document_ids: list[uuid.UUID] | None = None,
        *,
        force: bool = False,
        limit: int = 100,
    ) -> dict[str, Any]:
        run = self.get_latest_ready_run()
        if run is None:
            raise AppError(
                "No trained anomaly model is ready. Train the model first.",
                status_code=400,
            )

        if document_ids:
            ids = document_ids
        else:
            ids = list(
                self.db.scalars(
                    select(Invoice.document_id).order_by(Invoice.created_at.desc()).limit(limit)
                ).all()
            )

        results: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        for document_id in ids:
            try:
                results.append(
                    self.score_document(document_id, force=force, model_run_id=run.id)
                )
            except AppError as exc:
                errors.append({"document_id": str(document_id), "error": exc.message})
        return {
            "model_run_id": run.id,
            "scored": len(results),
            "errors": errors,
            "items": results,
        }

    def list_anomalies(
        self,
        *,
        status: str | None = None,
        min_score: float | None = None,
        vendor: str | None = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "detected_at",
        sort_order: str = "desc",
    ) -> dict[str, Any]:
        if page < 1:
            raise AppError("page must be >= 1.", status_code=400)
        if page_size < 1 or page_size > 100:
            raise AppError("page_size must be between 1 and 100.", status_code=400)

        sort_map = {
            "detected_at": DocumentAnomaly.detected_at,
            "anomaly_score": DocumentAnomaly.anomaly_score,
            "status": DocumentAnomaly.status,
        }
        sort_column = sort_map.get((sort_by or "detected_at").lower())
        if sort_column is None:
            raise AppError("Invalid sort_by.", status_code=400)
        order = (sort_order or "desc").lower()
        if order not in {"asc", "desc"}:
            raise AppError("Invalid sort_order.", status_code=400)

        filters = []
        if status:
            filters.append(DocumentAnomaly.status == status.strip().lower())
        if min_score is not None:
            filters.append(DocumentAnomaly.anomaly_score >= float(min_score))

        stmt = select(DocumentAnomaly)
        count_stmt = select(func.count()).select_from(DocumentAnomaly)
        if vendor:
            vendor_q = f"%{vendor.strip().lower()}%"
            invoice_docs = select(Invoice.document_id).where(
                func.lower(Invoice.vendor_name).like(vendor_q)
            )
            filters.append(DocumentAnomaly.document_id.in_(invoice_docs))

        if filters:
            stmt = stmt.where(*filters)
            count_stmt = count_stmt.where(*filters)

        total = self.db.scalar(count_stmt) or 0
        order_expr = asc(sort_column) if order == "asc" else desc(sort_column)
        rows = self.db.scalars(
            stmt.order_by(order_expr, desc(DocumentAnomaly.id))
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()

        items = [self._anomaly_payload(row) for row in rows]
        total_pages = ceil(total / page_size) if total else 0
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    def get_anomaly_for_document(self, document_id: uuid.UUID) -> dict[str, Any]:
        document = self.db.get(Document, document_id)
        if document is None:
            raise AppError("Document not found.", status_code=404)
        anomaly = self.db.scalar(
            select(DocumentAnomaly)
            .where(DocumentAnomaly.document_id == document_id)
            .order_by(DocumentAnomaly.detected_at.desc())
        )
        if anomaly is None:
            raise AppError("No anomaly result found for this document.", status_code=404)
        return self._anomaly_payload(anomaly, document=document)

    def list_model_runs(self, *, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        if page < 1:
            raise AppError("page must be >= 1.", status_code=400)
        if page_size < 1 or page_size > 100:
            raise AppError("page_size must be between 1 and 100.", status_code=400)
        total = self.db.scalar(select(func.count()).select_from(AnomalyModelRun)) or 0
        rows = self.db.scalars(
            select(AnomalyModelRun)
            .order_by(AnomalyModelRun.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return {
            "items": [self._run_payload(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def summary(self) -> dict[str, Any]:
        latest = self.get_latest_ready_run()
        analyzed = self.db.scalar(select(func.count()).select_from(DocumentAnomaly)) or 0
        requires_review = (
            self.db.scalar(
                select(func.count())
                .select_from(DocumentAnomaly)
                .where(DocumentAnomaly.status.in_(["anomaly", "requires_review"]))
            )
            or 0
        )
        return {
            "latest_model_run": self._run_payload(latest) if latest else None,
            "analyzed_documents": analyzed,
            "anomalies_requiring_attention": requires_review,
            "feature_names": list(FEATURE_NAMES),
            "disclaimer": (
                "Anomaly scores reflect statistical unusualness relative to learned patterns. "
                "They are not fraud determinations."
            ),
        }

    def _run_payload(self, run: AnomalyModelRun) -> dict[str, Any]:
        return {
            "id": run.id,
            "model_name": run.model_name,
            "model_version": run.model_version,
            "status": run.status,
            "trained_at": run.trained_at,
            "sample_count": run.sample_count,
            "feature_count": run.feature_count,
            "metadata": run.model_metadata,
            "created_at": run.created_at,
        }

    def _anomaly_payload(
        self,
        anomaly: DocumentAnomaly,
        *,
        document: Document | None = None,
        invoice: Invoice | None = None,
        run: AnomalyModelRun | None = None,
    ) -> dict[str, Any]:
        document = document or self.db.get(Document, anomaly.document_id)
        invoice = invoice or self.db.scalar(
            select(Invoice).where(Invoice.document_id == anomaly.document_id)
        )
        run = run or self.db.get(AnomalyModelRun, anomaly.model_run_id)
        return {
            "id": anomaly.id,
            "document_id": anomaly.document_id,
            "filename": document.original_filename if document else None,
            "document_type": document.document_type if document else None,
            "vendor_name": invoice.vendor_name if invoice else None,
            "invoice_number": invoice.invoice_number if invoice else None,
            "invoice_total": float(invoice.total_amount) if invoice and invoice.total_amount is not None else None,
            "model_run_id": anomaly.model_run_id,
            "model_name": run.model_name if run else None,
            "model_version": run.model_version if run else None,
            "anomaly_score": anomaly.anomaly_score,
            "status": anomaly.status,
            "reasons": anomaly.reasons or [],
            "feature_values": anomaly.feature_values,
            "detected_at": anomaly.detected_at,
        }
