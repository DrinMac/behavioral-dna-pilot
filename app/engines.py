from __future__ import annotations

from typing import Any

import numpy as np
from .config import METRICS
from .features import metric_vector

# Chi-square critical values for df=8 (the fixed number of Behavioral DNA metrics).
CHI95 = 15.50731305586545
CHI99 = 20.090235029663233


def clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, float(value)))


def z_score_engine(vector: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    scores: dict[str, float] = {}
    warning_count = 0
    failure_count = 0
    for metric in METRICS:
        score = abs((float(vector.get(metric, 0.0)) - float(baseline["mean"][metric])) / max(float(baseline["sd"][metric]), 1e-6))
        scores[metric] = score
        warning_count += int(score >= 2.0)
        failure_count += int(score >= 3.0)
    average_score = float(np.mean(list(scores.values()))) if scores else 0.0
    confidence = clamp(100.0 - ((average_score / 3.0) * 60.0 + (failure_count / len(METRICS)) * 40.0))
    return {
        "engine_name": "z_score",
        "score": round(max(scores.values()) if scores else 0.0, 6),
        "confidence": round(confidence, 6),
        "status": "normal" if failure_count == 0 and warning_count <= 1 else ("warning" if failure_count == 0 else "fail"),
        "details": {
            "z_scores": {metric: round(value, 6) for metric, value in scores.items()},
            "avg_abs_z": round(average_score, 6),
            "warn_count": warning_count,
            "fail_count": failure_count,
        },
    }


def envelope_engine(vector: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    pass_count = 0
    metric_scores: dict[str, Any] = {}
    for metric in METRICS:
        value = float(vector.get(metric, 0.0))
        lower = float(baseline["lower"][metric])
        upper = float(baseline["upper"][metric])
        average = float(baseline["mean"][metric])
        standard_deviation = max(float(baseline["sd"][metric]), 1e-6)
        inside = lower <= value <= upper
        pass_count += int(inside)
        z_value = abs((value - average) / standard_deviation)
        partial = 100.0 if inside else (60.0 if z_value <= 3.0 else (30.0 if z_value <= 4.0 else 0.0))
        metric_scores[metric] = {"inside": inside, "z": round(z_value, 6), "partial_score": partial}
    envelope_percentage = pass_count / len(METRICS) * 100.0
    confidence = float(np.mean([entry["partial_score"] for entry in metric_scores.values()]))
    return {
        "engine_name": "envelope",
        "score": round(envelope_percentage, 6),
        "confidence": round(confidence, 6),
        "status": "strong" if envelope_percentage >= 90.0 else ("monitor" if envelope_percentage >= 70.0 else "weak"),
        "details": {"envelope_pct": round(envelope_percentage, 6), "metric_scores": metric_scores},
    }


def mahalanobis_engine(vector: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    value_vector = metric_vector(vector)
    mean_vector = np.array([float(baseline["mean"][metric]) for metric in METRICS], dtype=float)
    standard_deviation = np.array([max(float(baseline["sd"][metric]), 1e-6) for metric in METRICS], dtype=float)
    standardized = (value_vector - mean_vector) / standard_deviation
    inverse_correlation = np.array(baseline.get("inv_corr") or np.eye(len(METRICS)), dtype=float)
    distance_squared = float(standardized.T @ inverse_correlation @ standardized)
    raw_contribution = np.abs(standardized * (inverse_correlation @ standardized))
    total_contribution = max(float(raw_contribution.sum()), 1e-9)
    contributions = {metric: round(float(value / total_contribution * 100.0), 6) for metric, value in zip(METRICS, raw_contribution)}
    if distance_squared <= CHI95:
        confidence = 100.0 - distance_squared / CHI95 * 20.0
        status = "normal"
    elif distance_squared <= CHI99:
        confidence = 80.0 - (distance_squared - CHI95) / (CHI99 - CHI95) * 30.0
        status = "elevated"
    else:
        confidence = clamp(50.0 - (distance_squared - CHI99) / 40.0 * 50.0, 0.0, 50.0)
        status = "abnormal"
    return {
        "engine_name": "mahalanobis",
        "score": round(distance_squared, 6),
        "confidence": round(clamp(confidence), 6),
        "status": status,
        "details": {
            "d2": round(distance_squared, 6),
            "chi95": round(CHI95, 6),
            "chi99": round(CHI99, 6),
            "contribution_pct": contributions,
        },
    }


def drift_engine(current_d2: float, previous_d2: float | None) -> dict[str, Any]:
    if previous_d2 is None:
        return {
            "engine_name": "drift",
            "score": 0.0,
            "confidence": 80.0,
            "status": "no_prior_window",
            "details": {"jump": 0.0, "previous_d2": None, "current_d2": current_d2},
        }
    jump = abs(float(current_d2) - float(previous_d2))
    if jump <= 5.0:
        confidence, status = 100.0, "stable"
    elif jump <= 15.0:
        confidence, status = 85.0 - (jump - 5.0) / 10.0 * 25.0, "gradual"
    elif jump <= 30.0:
        confidence, status = 60.0 - (jump - 15.0) / 15.0 * 35.0, "persistent"
    else:
        confidence, status = clamp(25.0 - (jump - 30.0) / 30.0 * 25.0, 0.0, 25.0), "sudden"
    return {
        "engine_name": "drift",
        "score": round(jump, 6),
        "confidence": round(clamp(confidence), 6),
        "status": status,
        "details": {"jump": round(jump, 6), "previous_d2": previous_d2, "current_d2": current_d2},
    }


def run_engines(vector: dict[str, Any], baseline: dict[str, Any], previous_d2: float | None = None) -> list[dict[str, Any]]:
    z_score = z_score_engine(vector, baseline)
    envelope = envelope_engine(vector, baseline)
    mahalanobis = mahalanobis_engine(vector, baseline)
    drift = drift_engine(float(mahalanobis["score"]), previous_d2)
    return [z_score, envelope, mahalanobis, drift]
