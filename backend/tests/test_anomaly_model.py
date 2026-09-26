"""Tests for IsolationForest anomaly model wrapper."""

from __future__ import annotations

import numpy as np

from app.core.exceptions import AppError
from app.services.anomaly_model import (
    decision_to_anomaly_score,
    score_status,
    score_vector,
    train_isolation_forest,
)
import pytest


def _matrix(n: int = 20):
    rng = np.random.default_rng(42)
    base = rng.normal(loc=100, scale=5, size=(n, 11))
    return base.tolist()


def test_insufficient_data():
    with pytest.raises(AppError):
        train_isolation_forest(_matrix(3), min_samples=10)


def test_deterministic_training():
    matrix = _matrix(20)
    a = train_isolation_forest(matrix, random_state=42, min_samples=10)
    b = train_isolation_forest(matrix, random_state=42, min_samples=10)
    score_a, status_a, _ = score_vector(a, matrix[0])
    score_b, status_b, _ = score_vector(b, matrix[0])
    assert score_a == score_b
    assert status_a == status_b
    assert a.model_name
    assert a.model_version


def test_score_mapping():
    assert 0.0 <= decision_to_anomaly_score(2.0) <= 1.0
    assert decision_to_anomaly_score(-2.0) > decision_to_anomaly_score(2.0)
    assert score_status(0.1) == "normal"
    assert score_status(0.4) == "unusual"
    assert score_status(0.6) == "anomaly"
    assert score_status(0.9) == "requires_review"
