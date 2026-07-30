from __future__ import annotations

from typing import Any

import numpy as np

from .config import METRICS
from .features import metric_vector


def _shrink_correlation_matrix(matrix: np.ndarray, shrinkage: float = 0.25) -> np.ndarray:
    if matrix.shape[0] < 2:
        return np.eye(len(METRICS))
    standard_deviation = np.maximum(matrix.std(axis=0, ddof=1), 1e-6)
    standardized = (matrix - matrix.mean(axis=0)) / standard_deviation
    with np.errstate(divide="ignore", invalid="ignore"):
        correlation = np.corrcoef(standardized, rowvar=False)
    if correlation.shape != (len(METRICS), len(METRICS)) or np.isnan(correlation).any():
        correlation = np.eye(len(METRICS))
    return (1.0 - shrinkage) * correlation + shrinkage * np.eye(len(METRICS))


def build_baseline(vectors: list[dict[str, Any]]) -> dict[str, Any]:
    if not vectors:
        raise ValueError("At least one feature vector is required.")
    matrix = np.vstack([metric_vector(vector) for vector in vectors])
    average = matrix.mean(axis=0)
    standard_deviation = matrix.std(axis=0, ddof=1) if matrix.shape[0] > 1 else np.maximum(np.abs(average) * 0.05, 1.0)
    standard_deviation = np.maximum(standard_deviation, np.maximum(np.abs(average) * 0.035, 0.5))
    lower = average - 2.0 * standard_deviation
    upper = average + 2.0 * standard_deviation
    correlation = _shrink_correlation_matrix(matrix)
    inverse_correlation = np.linalg.pinv(correlation)

    keydowns = int(sum(int(vector.get("keydown_count", 0)) for vector in vectors))
    sessions = len(vectors)
    readiness_confidence = min(100.0, 10.0 + sessions * 8.0 + min(50.0, keydowns / 30.0))
    readiness = {
        "session_count": sessions,
        "keydown_count": keydowns,
        "confidence": round(readiness_confidence, 4),
        "meets_minimum_for_pilot": sessions >= 2 and keydowns >= 250,
        "recommended_research_target": "At least 10 longitudinal sessions and approximately 3,000 keystrokes per participant.",
    }
    return {
        "mean": {metric: round(float(value), 6) for metric, value in zip(METRICS, average)},
        "sd": {metric: round(float(value), 6) for metric, value in zip(METRICS, standard_deviation)},
        "lower": {metric: round(float(value), 6) for metric, value in zip(METRICS, lower)},
        "upper": {metric: round(float(value), 6) for metric, value in zip(METRICS, upper)},
        "corr": correlation.round(6).tolist(),
        "inv_corr": inverse_correlation.round(6).tolist(),
        "readiness": readiness,
    }
