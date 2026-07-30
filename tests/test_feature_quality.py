from __future__ import annotations

from app.features import extract_features


def make_segment(start: float, interval: float, count: int, segment: str):
    events = []
    sequence = 0
    for index in range(count):
        down = start + index * interval
        events.extend([
            {
                "sequence_no": sequence,
                "event_type": "keydown",
                "key": "a",
                "code": "KeyA",
                "timestamp_ms": down,
                "field_name": "fixed_text",
                "segment": segment,
                "repeat": False,
            },
            {
                "sequence_no": sequence + 1,
                "event_type": "keyup",
                "key": "a",
                "code": "KeyA",
                "timestamp_ms": down + 70.0,
                "field_name": "fixed_text",
                "segment": segment,
                "repeat": False,
            },
        ])
        sequence += 2
    return events


def test_review_pause_is_separated_from_consistency_rhythm():
    events = make_segment(1000.0, 125.0, 20, "fixed:phase-0")
    # A correction phase begins much later. The phase boundary should prevent
    # the review interval from becoming a flight/digraph or consistency penalty.
    events += make_segment(20000.0, 125.0, 5, "fixed:phase-1")
    result = extract_features(events, "a" * 25)

    assert result["segment_count"] == 2
    assert result["pause_pattern"] < 500.0
    assert result["consistency_score"] > 95.0
    assert result["consistency_flight_count"] == 23
