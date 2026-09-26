"""Local IsolationForest model wrapper for anomaly detection."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any
import uuid

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from app.core.config import settings
from app.core.exceptions import AppError
from app.services.anomaly_features import FEATURE_NAMES


@dataclass
class TrainedAnomalyModel:
    model: IsolationForest
    scaler: StandardScaler
    feature_names: list[str]
    model_name: str
    model_version: str
    contamination: float
    random_state: int
    n_estimators: int
    sample_count: int

    def to_metadata(self) -> dict[str, Any]:
        return {
            "model_name": self.model_name,
            "model_version": self.model_version,
            "algorithm": "IsolationForest",
            "contamination": self.contamination,
            "random_state": self.random_state,
            "n_estimators": self.n_estimators,
            "sample_count": self.sample_count,
            "feature_names": list(self.feature_names),
            "feature_count": len(self.feature_names),
        }


def train_isolation_forest(
    matrix: list[list[float]],
    *,
    contamination: float | None = None,
    random_state: int | None = None,
    n_estimators: int | None = None,
    min_samples: int | None = None,
) -> TrainedAnomalyModel:
    min_required = min_samples if min_samples is not None else settings.ANOMALY_MIN_TRAINING_SAMPLES
    if len(matrix) < min_required:
        raise AppError(
            (
                f"Insufficient training data: need at least {min_required} invoices "
                f"with usable totals, found {len(matrix)}."
            ),
            status_code=400,
        )

    contamination_value = (
        contamination if contamination is not None else settings.ANOMALY_CONTAMINATION
    )
    contamination_value = min(max(float(contamination_value), 0.01), 0.5)
    seed = random_state if random_state is not None else settings.ANOMALY_RANDOM_STATE
    estimators = n_estimators if n_estimators is not None else settings.ANOMALY_N_ESTIMATORS

    array = np.asarray(matrix, dtype=float)
    scaler = StandardScaler()
    scaled = scaler.fit_transform(array)
    model = IsolationForest(
        n_estimators=int(estimators),
        contamination=contamination_value,
        random_state=int(seed),
        n_jobs=1,
    )
    model.fit(scaled)
    return TrainedAnomalyModel(
        model=model,
        scaler=scaler,
        feature_names=list(FEATURE_NAMES),
        model_name=settings.ANOMALY_MODEL_NAME,
        model_version=settings.ANOMALY_MODEL_VERSION,
        contamination=contamination_value,
        random_state=int(seed),
        n_estimators=int(estimators),
        sample_count=len(matrix),
    )


def decision_to_anomaly_score(decision: float) -> float:
    """Map IsolationForest decision_function to [0,1] anomaly score (higher = more unusual)."""
    # decision_function: higher => more normal. Squash to (0,1) anomaly likelihood.
    score = 1.0 / (1.0 + math.exp(float(decision) * 4.0))
    return max(0.0, min(1.0, score))


def score_status(anomaly_score: float) -> str:
    if anomaly_score < settings.ANOMALY_NORMAL_MAX:
        return "normal"
    if anomaly_score < settings.ANOMALY_UNUSUAL_MAX:
        return "unusual"
    if anomaly_score < settings.ANOMALY_ANOMALY_MAX:
        return "anomaly"
    return "requires_review"


def score_vector(trained: TrainedAnomalyModel, vector: list[float]) -> tuple[float, str, float]:
    array = np.asarray([vector], dtype=float)
    scaled = trained.scaler.transform(array)
    decision = float(trained.model.decision_function(scaled)[0])
    anomaly_score = decision_to_anomaly_score(decision)
    status = score_status(anomaly_score)
    return anomaly_score, status, decision


def save_trained_model(trained: TrainedAnomalyModel, run_id: uuid.UUID) -> Path:
    directory = settings.anomaly_model_dir_path
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{run_id}.joblib"
    payload = {
        "model": trained.model,
        "scaler": trained.scaler,
        "feature_names": trained.feature_names,
        "model_name": trained.model_name,
        "model_version": trained.model_version,
        "contamination": trained.contamination,
        "random_state": trained.random_state,
        "n_estimators": trained.n_estimators,
        "sample_count": trained.sample_count,
    }
    joblib.dump(payload, path)
    return path


def load_trained_model(path: Path | str) -> TrainedAnomalyModel:
    payload = joblib.load(path)
    return TrainedAnomalyModel(
        model=payload["model"],
        scaler=payload["scaler"],
        feature_names=list(payload["feature_names"]),
        model_name=payload["model_name"],
        model_version=payload["model_version"],
        contamination=float(payload["contamination"]),
        random_state=int(payload["random_state"]),
        n_estimators=int(payload["n_estimators"]),
        sample_count=int(payload["sample_count"]),
    )
