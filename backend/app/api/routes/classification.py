from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.user import User
from app.schemas.document import ClassificationModelStatusResponse, ClassificationTrainResponse
from app.services.audit_service import AuditService
from app.services.document_classification import DocumentClassificationService


router = APIRouter(prefix="/classification")


@router.post("/train", response_model=ClassificationTrainResponse)
def train_classification_model(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.CLASSIFICATION_TRAIN)),
) -> ClassificationTrainResponse:
    """Train the local ML document classifier from the starter dataset (admin only)."""
    AuditService(db).log(
        action="classification_training_started",
        user_id=user.id,
        resource_type="classification_model",
    )
    result = DocumentClassificationService(db).train_model()
    evaluation = None
    if result.evaluation is not None:
        evaluation = {
            "accuracy": result.evaluation.accuracy,
            "macro_precision": result.evaluation.macro_precision,
            "macro_recall": result.evaluation.macro_recall,
            "macro_f1": result.evaluation.macro_f1,
            "per_class": result.evaluation.per_class,
            "confusion_matrix": result.evaluation.confusion_matrix,
            "labels": result.evaluation.labels,
            "train_size": result.evaluation.train_size,
            "test_size": result.evaluation.test_size,
            "test_size_ratio": result.evaluation.test_size_ratio,
            "note": result.evaluation.note,
        }
    return ClassificationTrainResponse(
        status=result.status,
        example_count=result.example_count,
        labels=result.labels,
        model_available=result.model_available,
        model_version=result.model_version,
        trained_at=result.trained_at,
        message=result.message,
        evaluation=evaluation,
    )


@router.get("/model-status", response_model=ClassificationModelStatusResponse)
def get_classification_model_status(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.CLASSIFICATION_READ)),
) -> ClassificationModelStatusResponse:
    status = DocumentClassificationService(db).get_model_status()
    return ClassificationModelStatusResponse(
        model_available=status.model_available,
        model_version=status.model_version,
        trained_at=status.trained_at,
        training_example_count=status.training_example_count,
        supported_labels=status.supported_labels,
        algorithm=status.algorithm,
        evaluation_accuracy=status.evaluation_accuracy,
        evaluation_macro_f1=status.evaluation_macro_f1,
        evaluation_timestamp=status.evaluation_timestamp,
    )
