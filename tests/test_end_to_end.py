from __future__ import annotations

import os
import tempfile
from pathlib import Path

TEST_DB = Path(tempfile.gettempdir()) / "behavioral_dna_platform_test.db"
TEST_DB.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB}"
os.environ["RESEARCHER_PASSWORD"] = "research-test-password"
os.environ["SECRET_KEY"] = "test-secret-key-that-is-long-enough"
os.environ["TARGET_SESSIONS"] = "10"

from fastapi.testclient import TestClient

from app.config import FIXED_TEXT
from app.main import app

client = TestClient(app)


def event_stream(text: str, field_name: str, hold: float = 78.0, interval: float = 125.0, start: float = 1000.0):
    events = []
    sequence = 0
    timestamp = start
    for character in text:
        if character == " ":
            code = "Space"
        elif character.isalpha():
            code = f"Key{character.upper()}"
        elif character.isdigit():
            code = f"Digit{character}"
        else:
            code = "Punctuation"
        events.append({
            "sequence_no": sequence,
            "event_type": "keydown",
            "key": character,
            "code": code,
            "timestamp_ms": timestamp,
            "relative_time_ms": timestamp - start,
            "field_name": field_name,
            "is_backspace": False,
            "is_paste": False,
            "is_focus_event": False,
            "repeat": False,
        })
        sequence += 1
        events.append({
            "sequence_no": sequence,
            "event_type": "keyup",
            "key": character,
            "code": code,
            "timestamp_ms": timestamp + hold,
            "relative_time_ms": timestamp + hold - start,
            "field_name": field_name,
            "is_backspace": False,
            "is_paste": False,
            "is_focus_event": False,
            "repeat": False,
        })
        sequence += 1
        timestamp += interval
    return events


def reserve_and_register(age: int, occupation: str, timing: float = 125.0):
    device = {"browser": "Test Browser", "os": "Test OS", "device_type": "Desktop or laptop", "keyboard_type": "Laptop built-in keyboard"}
    reserved = client.post("/api/participants/reserve", json={"consent_accepted": True, "device": device})
    assert reserved.status_code == 200, reserved.text
    data = reserved.json()
    token = data["participant_token"]
    headers = {"X-Participant-Token": token}
    profile = {
        "age": age,
        "gender": "Prefer not to say",
        "occupation": occupation,
        "city": "Test City",
        "province": "Test Province",
        "education": "Bachelor's degree",
        "device": device,
    }
    registered = client.post("/api/participants/register", json=profile, headers=headers)
    assert registered.status_code == 200, registered.text
    return data, token, device, timing


def complete_session(token: str, device: dict, session_id: int, timing: float, include_initial: bool):
    headers = {"X-Participant-Token": token}
    free1 = "My country is a diverse nation with many communities and traditions."
    free2 = "I love my country because its people remain resilient and welcoming. Its history, landscapes, and cultures give me a strong sense of belonging."
    initial_text = "Accountant Test City Test Province"
    initial_events = event_stream(initial_text, "occupation", hold=timing * 0.55, interval=timing) if include_initial else []
    fixed_events = event_stream(FIXED_TEXT, "fixed_text", hold=timing * 0.55, interval=timing, start=5000.0)
    free_events = event_stream(free1, "free_text_1", hold=timing * 0.55, interval=timing, start=10000.0)
    second = event_stream(free2, "free_text_2", hold=timing * 0.55, interval=timing, start=30000.0)
    offset = len(free_events)
    for event in second:
        event["sequence_no"] += offset
    free_events.extend(second)
    payload = {
        "device": device,
        "initial_text": initial_text if include_initial else "",
        "fixed_text": FIXED_TEXT,
        "free_text_1": free1,
        "free_text_2": free2,
        "initial_events": initial_events,
        "fixed_events": fixed_events,
        "free_events": free_events,
    }
    analyzed = client.post(f"/api/participants/sessions/{session_id}/analyze", json=payload, headers=headers)
    assert analyzed.status_code == 200, analyzed.text
    metrics = analyzed.json()["metrics"]
    assert {"fixed", "free", "combined"}.issubset(metrics)
    assert len([key for key in metrics["combined"] if key in {"hold_time", "flight_time", "digraph_latency", "trigraph_latency", "typing_speed", "error_rate", "pause_pattern", "consistency_score"}]) == 8
    submitted = client.post(f"/api/participants/sessions/{session_id}/submit", headers=headers)
    assert submitted.status_code == 200, submitted.text
    return submitted.json()


def start_and_complete(token: str, device: dict, timing: float):
    headers = {"X-Participant-Token": token}
    started = client.post("/api/participants/sessions/start", json={"device": device}, headers=headers)
    assert started.status_code == 200, started.text
    session = started.json()
    complete_session(token, device, session["id"], timing, include_initial=False)
    return session


def test_participant_interface_is_rebuilt_guided_flow():
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers.get("cache-control") == "no-store, no-cache, must-revalidate, max-age=0"
    assert "participant-v2.css?v=4.2.0" in response.text
    assert "participant-v2.js?v=4.2.0" in response.text
    assert "Continuous Authentication Study" in response.text
    assert "<nav" not in response.text.lower()

    script = client.get("/static/participant-v2.js?v=4.2.0")
    assert script.status_code == 200
    assert "Type the passage exactly as shown" in script.text
    assert "Pause & Review Difference" in script.text
    assert "First difference at character" in script.text
    assert "Do Another Typing Session" in script.text
    assert "Your eight keystroke metrics are ready" in script.text


def test_full_longitudinal_research_workflow():
    p1, token1, device1, _ = reserve_and_register(34, "Accountant", 125.0)
    s1 = p1["session"]
    complete_session(token1, device1, s1["id"], 125.0, include_initial=True)
    s2 = start_and_complete(token1, device1, 128.0)
    s3 = start_and_complete(token1, device1, 122.0)

    p2, token2, device2, _ = reserve_and_register(29, "Engineer", 205.0)
    p2s1 = p2["session"]
    complete_session(token2, device2, p2s1["id"], 205.0, include_initial=True)

    login = client.post("/api/research/login", json={"password": "research-test-password"})
    assert login.status_code == 200

    participants = client.get("/api/research/participants")
    assert participants.status_code == 200
    p1_row = next(row for row in participants.json() if row["participant_code"] == p1["participant_code"])

    baseline_response = client.post("/api/research/baselines", json={
        "participant_id": p1_row["id"],
        "session_ids": [s1["id"], s2["id"]],
        "activity_scope": "combined",
        "name": "P1 Sessions 1-2 Enrollment Baseline",
    })
    assert baseline_response.status_code == 200, baseline_response.text
    baseline = baseline_response.json()
    assert baseline["baseline"]["readiness"]["session_count"] == 2

    overlap = client.post("/api/research/evaluations", json={
        "baseline_id": baseline["id"],
        "test_session_ids": [s1["id"]],
        "activity_scope": "combined",
    })
    assert overlap.status_code == 400

    evaluation = client.post("/api/research/evaluations", json={
        "baseline_id": baseline["id"],
        "test_session_ids": [s3["id"], p2s1["id"]],
        "activity_scope": "combined",
        "name": "Genuine and impostor holdout",
        "config": {
            "active_engines": {"z_score": True, "envelope": True, "mahalanobis": True, "drift": True},
            "fusion_method": "weighted",
            "weights": {"z_score": 1, "envelope": 1, "mahalanobis": 3, "drift": 2},
            "thresholds": {"genuine": 85, "genuine_min": 70, "monitor": 70, "monitor_min": 45, "step_up": 55, "lock_override": 25},
        },
    })
    assert evaluation.status_code == 200, evaluation.text
    body = evaluation.json()
    assert body["run"]["summary"]["n"] == 2
    assert all(len(row["engine_results"]) == 4 for row in body["results"])
    assert {row["expected_label"] for row in body["results"]} == {"genuine", "impostor"}

    export = client.get("/api/research/export")
    assert export.status_code == 200
    assert export.headers["content-type"] == "application/zip"
    assert len(export.content) > 1000
