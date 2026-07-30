from __future__ import annotations

from typing import Any

import numpy as np


def _roc_auc_eer(labels: np.ndarray, scores: np.ndarray) -> tuple[float | None, float | None]:
    """Compute ROC AUC and EER without an external machine-learning dependency."""
    positives = int(labels.sum())
    negatives = int(len(labels) - positives)
    if positives == 0 or negatives == 0:
        return None, None

    thresholds = np.r_[np.inf, np.unique(scores)[::-1], -np.inf]
    points: list[tuple[float, float]] = []
    for threshold in thresholds:
        predicted = scores >= threshold
        true_positive = int(np.sum(predicted & (labels == 1)))
        false_positive = int(np.sum(predicted & (labels == 0)))
        true_positive_rate = true_positive / positives
        false_positive_rate = false_positive / negatives
        points.append((false_positive_rate, true_positive_rate))

    # Remove duplicate FPR points by retaining the largest TPR, then integrate.
    consolidated: dict[float, float] = {}
    for false_positive_rate, true_positive_rate in points:
        consolidated[false_positive_rate] = max(consolidated.get(false_positive_rate, 0.0), true_positive_rate)
    ordered = sorted(consolidated.items())
    false_positive_rates = np.array([point[0] for point in ordered], dtype=float)
    true_positive_rates = np.array([point[1] for point in ordered], dtype=float)
    auc_value = float(np.trapezoid(true_positive_rates, false_positive_rates))

    false_negative_rates = 1.0 - true_positive_rates
    index = int(np.nanargmin(np.abs(false_positive_rates - false_negative_rates)))
    eer = float((false_positive_rates[index] + false_negative_rates[index]) / 2.0)
    return auc_value, eer


def compute_evaluation_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [row for row in results if row.get("expected_label") in {"genuine", "impostor"}]
    if not rows:
        return {"n": 0, "TP": 0, "TN": 0, "FP": 0, "FN": 0}

    true_positive = sum(1 for row in rows if row["expected_label"] == "impostor" and row["decision"]["predicted_label"] == "impostor")
    true_negative = sum(1 for row in rows if row["expected_label"] == "genuine" and row["decision"]["predicted_label"] == "genuine")
    false_positive = sum(1 for row in rows if row["expected_label"] == "genuine" and row["decision"]["predicted_label"] == "impostor")
    false_negative = sum(1 for row in rows if row["expected_label"] == "impostor" and row["decision"]["predicted_label"] == "genuine")
    count = len(rows)

    def divide(numerator: float, denominator: float) -> float | None:
        return None if denominator == 0 else numerator / denominator

    precision = divide(true_positive, true_positive + false_positive)
    recall = divide(true_positive, true_positive + false_negative)
    specificity = divide(true_negative, true_negative + false_positive)
    accuracy = divide(true_positive + true_negative, count)
    far = divide(false_positive, false_positive + true_negative)
    frr = divide(false_negative, false_negative + true_positive)
    f1 = None if precision is None or recall is None or precision + recall == 0 else 2.0 * precision * recall / (precision + recall)
    balanced_accuracy = None if recall is None or specificity is None else (recall + specificity) / 2.0

    labels = np.array([1 if row["expected_label"] == "impostor" else 0 for row in rows], dtype=int)
    anomaly_scores = np.array([1.0 - float(row["decision"].get("overall_confidence", 0.0)) / 100.0 for row in rows], dtype=float)
    auc_value, eer = _roc_auc_eer(labels, anomaly_scores)

    return {
        "n": count,
        "TP": true_positive,
        "TN": true_negative,
        "FP": false_positive,
        "FN": false_negative,
        "accuracy": accuracy,
        "balanced_accuracy": balanced_accuracy,
        "precision": precision,
        "recall_tpr": recall,
        "specificity_tnr": specificity,
        "f1": f1,
        "far_fpr": far,
        "frr_fnr": frr,
        "auc": auc_value,
        "eer": eer,
    }
