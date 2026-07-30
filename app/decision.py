from __future__ import annotations

from statistics import median
from typing import Any

import numpy as np

from .config import DEFAULT_ENGINE_CONFIG


def _selected_results(engine_results: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    active = config.get("active_engines", DEFAULT_ENGINE_CONFIG["active_engines"])
    selected = [result for result in engine_results if bool(active.get(result["engine_name"], False))]
    return selected or [result for result in engine_results if result["engine_name"] == "z_score"]


def fuse(engine_results: list[dict[str, Any]], config: dict[str, Any]) -> float:
    values = [float(result.get("confidence", 0.0)) for result in engine_results]
    method = config.get("fusion_method", "median")
    if method == "mean":
        return float(np.mean(values))
    if method == "minimum":
        return float(min(values))
    if method == "weighted":
        weight_config = config.get("weights", {})
        weights = [max(0.0, float(weight_config.get(result["engine_name"], 1.0))) for result in engine_results]
        total = sum(weights) or 1.0
        return float(sum(value * weight for value, weight in zip(values, weights)) / total)
    if method == "majority":
        cutoff = float(config.get("majority_cutoff", 70.0))
        return float(sum(1 for value in values if value >= cutoff) / len(values) * 100.0)
    return float(median(values))


def make_decision(engine_results: list[dict[str, Any]], config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or DEFAULT_ENGINE_CONFIG
    selected = _selected_results(engine_results, config)
    overall = fuse(selected, config)
    minimum = min(float(result.get("confidence", 0.0)) for result in selected)
    thresholds = {**DEFAULT_ENGINE_CONFIG["thresholds"], **config.get("thresholds", {})}

    if minimum < float(thresholds["lock_override"]):
        action = "Lock"
        classification = "Likely Impostor"
        rule = f"Safety override: minimum selected-engine confidence {minimum:.2f}% is below {thresholds['lock_override']}%."
    elif overall >= float(thresholds["genuine"]) and minimum >= float(thresholds["genuine_min"]):
        action = "Genuine"
        classification = "Genuine"
        rule = f"Fused confidence {overall:.2f}% and minimum confidence {minimum:.2f}% meet the Genuine criteria."
    elif overall >= float(thresholds["monitor"]) and minimum >= float(thresholds["monitor_min"]):
        action = "Monitor"
        classification = "Likely Genuine / Mild Anomaly"
        rule = f"Fused confidence {overall:.2f}% meets Monitor criteria but not Genuine criteria."
    elif overall >= float(thresholds["step_up"]):
        action = "Step-up"
        classification = "Uncertain / Verify Again"
        rule = f"Fused confidence {overall:.2f}% requires additional verification."
    else:
        action = "Lock"
        classification = "Likely Impostor"
        rule = f"Fused confidence {overall:.2f}% is below the Step-up threshold."

    return {
        "final_action": action,
        "predicted_label": "impostor" if action == "Lock" else "genuine",
        "classification": classification,
        "overall_confidence": round(overall, 6),
        "minimum_confidence": round(minimum, 6),
        "selected_engines": [result["engine_name"] for result in selected],
        "fusion_method": config.get("fusion_method", "median"),
        "rule_text": rule,
    }
