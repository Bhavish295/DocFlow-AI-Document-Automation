"""Local TF-IDF + LogisticRegression document classifier (no cloud / no transformers)."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Protocol

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

from app.core.config import BACKEND_ROOT, settings
from app.core.exceptions import AppError
from app.models.document import DocumentType
from app.services.classification import ClassificationResult


SUPPORTED_LABELS = tuple(item.value for item in DocumentType)
STARTER_DATASET_PATH = (
    BACKEND_ROOT / "app" / "data" / "classification" / "starter_training_set.json"
)
MODEL_FILENAME = "document_classifier.joblib"
DEFAULT_TEST_SIZE = 0.25


class MlDocumentClassifierProtocol(Protocol):
    def predict(self, text: str) -> ClassificationResult | None:
        """Return a prediction when a trained model is available."""

    def is_available(self) -> bool:
        """Whether a trained model can be loaded and used."""


@dataclass(frozen=True)
class TrainingExample:
    text: str
    label: str


@dataclass
class EvaluationMetrics:
    """Holdout metrics on the local synthetic evaluation split only."""

    accuracy: float
    macro_precision: float
    macro_recall: float
    macro_f1: float
    per_class: dict[str, dict[str, float]]
    confusion_matrix: list[list[int]]
    labels: list[str]
    train_size: int
    test_size: int
    test_size_ratio: float
    note: str = (
        "Metrics are measured on a local synthetic holdout split and are not "
        "production accuracy."
    )


@dataclass
class TrainResult:
    status: str
    example_count: int
    labels: list[str]
    model_available: bool
    model_version: str
    trained_at: str
    message: str
    evaluation: EvaluationMetrics | None = None


@dataclass
class ModelStatus:
    model_available: bool
    model_version: str | None
    trained_at: str | None
    training_example_count: int | None
    supported_labels: list[str]
    algorithm: str
    evaluation_accuracy: float | None = None
    evaluation_macro_f1: float | None = None
    evaluation_timestamp: str | None = None


def load_starter_training_examples(path: Path | None = None) -> list[TrainingExample]:
    dataset_path = path or STARTER_DATASET_PATH
    if not dataset_path.exists():
        raise AppError(f"Training dataset not found: {dataset_path.name}", status_code=500)

    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    raw_examples = payload.get("examples")
    if not isinstance(raw_examples, list) or not raw_examples:
        raise AppError("Training dataset has no examples.", status_code=500)

    examples: list[TrainingExample] = []
    for index, item in enumerate(raw_examples):
        if not isinstance(item, dict):
            raise AppError(f"Invalid training example at index {index}.", status_code=500)
        label = str(item.get("label") or "").strip().lower()
        text = str(item.get("text") or "").strip()
        if label not in SUPPORTED_LABELS:
            raise AppError(f"Unsupported training label: {label}", status_code=500)
        if not text:
            raise AppError(f"Empty training text for label {label}.", status_code=500)
        examples.append(TrainingExample(text=text, label=label))

    present = {example.label for example in examples}
    missing = [label for label in SUPPORTED_LABELS if label not in present]
    if missing:
        raise AppError(
            "Training dataset is missing labels: " + ", ".join(missing),
            status_code=500,
        )
    return examples


def dataset_label_counts(examples: list[TrainingExample]) -> dict[str, int]:
    counts = Counter(item.label for item in examples)
    return {label: int(counts.get(label, 0)) for label in SUPPORTED_LABELS}


def split_examples(
    examples: list[TrainingExample],
    *,
    test_size: float = DEFAULT_TEST_SIZE,
    random_state: int | None = None,
) -> tuple[list[TrainingExample], list[TrainingExample]]:
    """Deterministic stratified train/test split to avoid evaluating on training text."""
    if len(examples) < len(SUPPORTED_LABELS) * 2:
        raise AppError(
            "Need at least two examples per label for a stratified train/test split.",
            status_code=400,
        )

    seed = settings.CLASSIFICATION_RANDOM_STATE if random_state is None else random_state
    texts = [item.text for item in examples]
    labels = [item.label for item in examples]
    train_texts, test_texts, train_labels, test_labels = train_test_split(
        texts,
        labels,
        test_size=test_size,
        random_state=int(seed),
        stratify=labels,
    )
    train = [
        TrainingExample(text=text, label=label)
        for text, label in zip(train_texts, train_labels, strict=True)
    ]
    test = [
        TrainingExample(text=text, label=label)
        for text, label in zip(test_texts, test_labels, strict=True)
    ]
    return train, test


def evaluate_classifier(
    pipeline: Pipeline,
    test_examples: list[TrainingExample],
    *,
    train_size: int,
    test_size_ratio: float,
) -> EvaluationMetrics:
    if not test_examples:
        raise AppError("Evaluation requires a non-empty test set.", status_code=500)

    texts = [item.text for item in test_examples]
    y_true = [item.label for item in test_examples]
    y_pred = [str(label) for label in pipeline.predict(texts)]
    label_order = list(SUPPORTED_LABELS)

    report = classification_report(
        y_true,
        y_pred,
        labels=label_order,
        output_dict=True,
        zero_division=0,
    )
    matrix = confusion_matrix(y_true, y_pred, labels=label_order)

    per_class: dict[str, dict[str, float]] = {}
    for label in label_order:
        row = report.get(label, {})
        per_class[label] = {
            "precision": round(float(row.get("precision", 0.0)), 4),
            "recall": round(float(row.get("recall", 0.0)), 4),
            "f1": round(float(row.get("f1-score", 0.0)), 4),
            "support": int(row.get("support", 0)),
        }

    return EvaluationMetrics(
        accuracy=round(float(accuracy_score(y_true, y_pred)), 4),
        macro_precision=round(
            float(precision_score(y_true, y_pred, labels=label_order, average="macro", zero_division=0)),
            4,
        ),
        macro_recall=round(
            float(recall_score(y_true, y_pred, labels=label_order, average="macro", zero_division=0)),
            4,
        ),
        macro_f1=round(
            float(f1_score(y_true, y_pred, labels=label_order, average="macro", zero_division=0)),
            4,
        ),
        per_class=per_class,
        confusion_matrix=matrix.astype(int).tolist(),
        labels=label_order,
        train_size=int(train_size),
        test_size=len(test_examples),
        test_size_ratio=float(test_size_ratio),
    )


def build_classifier_pipeline(*, random_state: int | None = None) -> Pipeline:
    seed = settings.CLASSIFICATION_RANDOM_STATE if random_state is None else random_state
    return Pipeline(
        steps=[
            (
                "tfidf",
                TfidfVectorizer(
                    lowercase=True,
                    ngram_range=(1, 2),
                    min_df=1,
                    max_features=8000,
                ),
            ),
            (
                "clf",
                LogisticRegression(
                    max_iter=2000,
                    random_state=int(seed),
                    solver="lbfgs",
                ),
            ),
        ]
    )


class TfidfLogisticDocumentClassifier:
    """Deterministic local ML classifier using TF-IDF features + LogisticRegression."""

    def __init__(self, model_dir: Path | None = None) -> None:
        self.model_dir = model_dir or settings.classification_model_dir_path
        self._pipeline: Pipeline | None = None
        self._metadata: dict[str, Any] = {}

    @property
    def model_path(self) -> Path:
        return self.model_dir / MODEL_FILENAME

    def is_available(self) -> bool:
        return self.model_path.exists()

    def train(
        self,
        examples: list[TrainingExample] | None = None,
        *,
        random_state: int | None = None,
        test_size: float = DEFAULT_TEST_SIZE,
    ) -> TrainResult:
        all_examples = examples if examples is not None else load_starter_training_examples()
        if len(all_examples) < len(SUPPORTED_LABELS):
            raise AppError("Not enough training examples to train the classifier.", status_code=400)

        train_examples, test_examples = split_examples(
            all_examples,
            test_size=test_size,
            random_state=random_state,
        )
        texts = [item.text for item in train_examples]
        labels = [item.label for item in train_examples]
        pipeline = build_classifier_pipeline(random_state=random_state)
        pipeline.fit(texts, labels)

        evaluation = evaluate_classifier(
            pipeline,
            test_examples,
            train_size=len(train_examples),
            test_size_ratio=float(test_size),
        )

        trained_at = datetime.now(timezone.utc).isoformat()
        metadata = {
            "algorithm": "tfidf_logistic_regression",
            "model_version": settings.CLASSIFICATION_MODEL_VERSION,
            "trained_at": trained_at,
            "training_example_count": len(all_examples),
            "train_size": len(train_examples),
            "test_size": len(test_examples),
            "supported_labels": list(SUPPORTED_LABELS),
            "random_state": int(
                settings.CLASSIFICATION_RANDOM_STATE if random_state is None else random_state
            ),
            "dataset": "starter_training_set",
            "evaluation": asdict(evaluation),
            "evaluation_timestamp": trained_at,
        }
        self._save(pipeline, metadata)
        self._pipeline = pipeline
        self._metadata = metadata
        return TrainResult(
            status="trained",
            example_count=len(all_examples),
            labels=sorted({item.label for item in all_examples}),
            model_available=True,
            model_version=str(metadata["model_version"]),
            trained_at=trained_at,
            message=(
                "Local ML document classifier trained successfully with stratified holdout "
                "evaluation. Metrics are for the local synthetic dataset only, not production."
            ),
            evaluation=evaluation,
        )

    def predict(self, text: str) -> ClassificationResult | None:
        pipeline = self._ensure_loaded()
        if pipeline is None:
            return None

        cleaned = (text or "").strip()
        if not cleaned:
            return ClassificationResult(document_type=DocumentType.OTHER.value, confidence=0.2)

        predicted = str(pipeline.predict([cleaned])[0])
        confidence = self._confidence_for(pipeline, cleaned, predicted)
        return ClassificationResult(document_type=predicted, confidence=confidence)

    def get_status(self) -> ModelStatus:
        available = self.is_available()
        metadata = self._metadata if self._metadata else self._load_metadata_only()
        evaluation = metadata.get("evaluation") if available else None
        evaluation = evaluation if isinstance(evaluation, dict) else {}
        return ModelStatus(
            model_available=available,
            model_version=metadata.get("model_version") if available else None,
            trained_at=metadata.get("trained_at") if available else None,
            training_example_count=(
                int(metadata["training_example_count"])
                if available and metadata.get("training_example_count") is not None
                else None
            ),
            supported_labels=list(SUPPORTED_LABELS),
            algorithm=str(metadata.get("algorithm") or "tfidf_logistic_regression"),
            evaluation_accuracy=(
                float(evaluation["accuracy"]) if evaluation.get("accuracy") is not None else None
            ),
            evaluation_macro_f1=(
                float(evaluation["macro_f1"]) if evaluation.get("macro_f1") is not None else None
            ),
            evaluation_timestamp=(
                str(metadata.get("evaluation_timestamp"))
                if available and metadata.get("evaluation_timestamp")
                else None
            ),
        )

    def _confidence_for(self, pipeline: Pipeline, text: str, predicted: str) -> float:
        classifier = pipeline.named_steps["clf"]
        if not hasattr(classifier, "predict_proba"):
            raise AppError("Classifier does not expose probabilities.", status_code=500)
        probabilities = pipeline.predict_proba([text])[0]
        classes = list(classifier.classes_)
        if predicted not in classes:
            return 0.0
        index = classes.index(predicted)
        return round(float(max(0.0, min(1.0, probabilities[index]))), 4)

    def _ensure_loaded(self) -> Pipeline | None:
        if self._pipeline is not None:
            return self._pipeline
        if not self.is_available():
            return None
        payload = joblib.load(self.model_path)
        self._pipeline = payload["pipeline"]
        self._metadata = dict(payload.get("metadata") or {})
        return self._pipeline

    def _save(self, pipeline: Pipeline, metadata: dict[str, Any]) -> Path:
        self.model_dir.mkdir(parents=True, exist_ok=True)
        path = self.model_path
        joblib.dump({"pipeline": pipeline, "metadata": metadata}, path)
        return path

    def _load_metadata_only(self) -> dict[str, Any]:
        if not self.is_available():
            return {}
        try:
            payload = joblib.load(self.model_path)
            return dict(payload.get("metadata") or {})
        except Exception:
            return {}


_default_ml_classifier: TfidfLogisticDocumentClassifier | None = None


def get_default_ml_classifier() -> TfidfLogisticDocumentClassifier:
    global _default_ml_classifier
    if _default_ml_classifier is None:
        _default_ml_classifier = TfidfLogisticDocumentClassifier()
    return _default_ml_classifier


def reset_default_ml_classifier() -> None:
    """Test helper to clear the process-local classifier cache."""
    global _default_ml_classifier
    _default_ml_classifier = None
