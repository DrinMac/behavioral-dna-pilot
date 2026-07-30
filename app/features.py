from __future__ import annotations

from collections import defaultdict, deque
from statistics import mean, stdev
from typing import Any

import numpy as np

from .config import METRICS


def _avg(values: list[float]) -> float:
    return float(mean(values)) if values else 0.0


def _sd(values: list[float]) -> float:
    return float(stdev(values)) if len(values) >= 2 else 0.0


def _segment(event: dict[str, Any]) -> str:
    return str(event.get("segment") or f"{event.get('activity_type', '')}:{event.get('field_name', '')}")


def _is_timing_event(event: dict[str, Any]) -> bool:
    return event.get("event_type") in {"keydown", "keyup"} and not event.get("is_focus_event") and not event.get("is_paste")


def _is_printable_key(event: dict[str, Any]) -> bool:
    key = str(event.get("key") or "")
    code = str(event.get("code") or "")
    return len(key) == 1 or code.startswith(("Key", "Digit", "Numpad")) or code == "Space"


def _build_strokes(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    queues: dict[tuple[str, str], deque[dict[str, Any]]] = defaultdict(deque)
    strokes: list[dict[str, Any]] = []
    for event in sorted(events, key=lambda e: (float(e.get("timestamp_ms", 0)), int(e.get("sequence_no", 0)))):
        if not _is_timing_event(event):
            continue
        code = str(event.get("code") or event.get("key") or "Unknown")
        seg = _segment(event)
        key = (seg, code)
        if event.get("event_type") == "keydown":
            if event.get("repeat"):
                continue
            queues[key].append(event)
        elif queues[key]:
            down = queues[key].popleft()
            down_t = float(down.get("timestamp_ms", 0))
            up_t = float(event.get("timestamp_ms", 0))
            if up_t >= down_t:
                strokes.append(
                    {
                        "segment": seg,
                        "code": code,
                        "key": down.get("key"),
                        "down": down_t,
                        "up": up_t,
                        "hold": up_t - down_t,
                        "printable": _is_printable_key(down),
                    }
                )
    return sorted(strokes, key=lambda s: (s["segment"], s["down"]))


def extract_features(events: list[dict[str, Any]], typed_text: str = "") -> dict[str, float | int | str | list[str]]:
    """Extract eight aggregate keystroke metrics from real browser telemetry.

    Segments reset timing chains between form fields and typing activities, preventing
    page transitions or focus changes from being counted as digraphs, trigraphs, or pauses.
    Flight time is UD (current keydown minus previous keyup) and may legitimately be negative
    when keystrokes overlap.
    """
    if not events:
        return {
            **{metric: 0.0 for metric in METRICS},
            "feature_version": "4.2",
            "pause_threshold_ms": 500.0,
            "raw_event_count": 0,
            "keydown_count": 0,
            "duration_sec": 0.0,
            "char_count": len(typed_text),
            "word_count": len(typed_text.split()),
            "backspace_count": 0,
            "paste_count": 0,
            "sample_warnings": ["No keystroke events were captured."],
        }

    ordered = sorted(events, key=lambda e: (float(e.get("timestamp_ms", 0)), int(e.get("sequence_no", 0))))
    strokes = _build_strokes(ordered)
    by_segment: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for stroke in strokes:
        by_segment[stroke["segment"]].append(stroke)

    holds: list[float] = []
    flights: list[float] = []
    digraphs: list[float] = []
    trigraphs: list[float] = []
    active_duration_ms = 0.0
    for segment_strokes in by_segment.values():
        segment_strokes.sort(key=lambda s: s["down"])
        holds.extend(float(s["hold"]) for s in segment_strokes)
        if segment_strokes:
            active_duration_ms += max(0.0, segment_strokes[-1]["up"] - segment_strokes[0]["down"])
        for index in range(1, len(segment_strokes)):
            flights.append(float(segment_strokes[index]["down"] - segment_strokes[index - 1]["up"]))
            digraphs.append(float(segment_strokes[index]["down"] - segment_strokes[index - 1]["down"]))
        for index in range(2, len(segment_strokes)):
            trigraphs.append(float(segment_strokes[index]["down"] - segment_strokes[index - 2]["down"]))

    keydowns = [e for e in ordered if e.get("event_type") == "keydown" and not e.get("repeat")]
    printable_downs = [e for e in keydowns if _is_printable_key(e)]
    backspaces = sum(1 for e in keydowns if e.get("is_backspace") or e.get("key") in {"Backspace", "Delete"})
    paste_events = sum(1 for e in ordered if e.get("is_paste") or e.get("event_type") == "paste")

    duration_sec = max(active_duration_ms / 1000.0, 1e-6)
    char_count = len(typed_text or "")
    typing_speed = (char_count / 5.0) / max(duration_sec / 60.0, 1e-6)
    error_rate = backspaces / max(len(printable_downs) + backspaces, 1) * 100.0

    positive_flights = [value for value in flights if value >= 0]
    pauses = [value for value in positive_flights if value >= 500.0]
    pause_pattern = _avg(pauses) if pauses else (float(np.percentile(positive_flights, 75)) if positive_flights else 0.0)

    # Pauses are represented separately by pause_pattern. Excluding flights at or
    # above the pause threshold prevents a single reading/review pause from being
    # counted twice and dominating the motor-rhythm consistency score.
    rhythm_flights = [value for value in flights if abs(value) < 500.0]
    hold_cv = _sd(holds) / max(abs(_avg(holds)), 1e-6)
    flight_cv = _sd(rhythm_flights) / max(_avg([abs(v) for v in rhythm_flights]), 1e-6)
    consistency_score = max(0.0, min(100.0, 100.0 - hold_cv * 30.0 - flight_cv * 20.0 - paste_events * 2.0))

    warnings: list[str] = []
    if len(strokes) < 20:
        warnings.append("Small keystroke sample; interpret the metrics cautiously.")
    if paste_events:
        warnings.append("One or more paste events were detected.")
    if not holds:
        warnings.append("No complete keydown-keyup pairs were available.")

    return {
        "feature_version": "4.2",
        "pause_threshold_ms": 500.0,
        "consistency_definition": "hold CV plus sub-500-ms flight CV; longer flights are represented by pause_pattern",
        "hold_time": round(_avg(holds), 6),
        "flight_time": round(_avg(flights), 6),
        "digraph_latency": round(_avg(digraphs), 6),
        "trigraph_latency": round(_avg(trigraphs), 6),
        "typing_speed": round(float(typing_speed), 6),
        "error_rate": round(float(error_rate), 6),
        "pause_pattern": round(float(pause_pattern), 6),
        "consistency_score": round(float(consistency_score), 6),
        "raw_event_count": len(ordered),
        "keydown_count": len(keydowns),
        "stroke_count": len(strokes),
        "duration_sec": round(float(duration_sec), 6),
        "char_count": char_count,
        "word_count": len((typed_text or "").split()),
        "backspace_count": backspaces,
        "paste_count": paste_events,
        "consistency_flight_count": len(rhythm_flights),
        "segment_count": len(by_segment),
        "sample_warnings": warnings,
    }


def metric_vector(vector: dict[str, Any]) -> np.ndarray:
    return np.array([float(vector.get(metric, 0.0)) for metric in METRICS], dtype=float)
