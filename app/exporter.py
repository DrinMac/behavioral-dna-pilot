from __future__ import annotations

import csv
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import (
    Baseline,
    EvaluationResult,
    EvaluationRun,
    MetricVector,
    Participant,
    ParticipantDevice,
    RawKeystrokeEvent,
    StudySession,
)


def _serialize(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _write_csv(path: Path, rows: Iterable[Any], columns: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        for row in rows:
            writer.writerow([_serialize(getattr(row, column)) for column in columns])


def build_export_zip(db: Session) -> Path:
    temp_dir = Path(tempfile.mkdtemp(prefix="behavioral_dna_export_"))
    definitions = [
        (
            "participants.csv",
            db.scalars(select(Participant).order_by(Participant.id)).all(),
            ["id", "participant_code", "age", "gender", "occupation", "city", "province", "education", "consent_accepted", "consent_version", "profile_completed", "status", "created_at", "last_seen_at"],
        ),
        (
            "participant_devices.csv",
            db.scalars(select(ParticipantDevice).order_by(ParticipantDevice.id)).all(),
            ["id", "participant_id", "browser", "os", "device_type", "created_at", "last_seen_at", "revoked"],
        ),
        (
            "study_sessions.csv",
            db.scalars(select(StudySession).order_by(StudySession.id)).all(),
            ["id", "session_code", "participant_id", "session_number", "status", "browser", "os", "device_type", "keyboard_type", "fixed_text", "free_text_1", "free_text_2", "fixed_match_ratio", "quality_json", "started_at", "analyzed_at", "completed_at"],
        ),
        (
            "metric_vectors.csv",
            db.scalars(select(MetricVector).order_by(MetricVector.id)).all(),
            ["id", "session_id", "participant_id", "activity_type", "vector_json", "created_at"],
        ),
        (
            "raw_keystroke_events.csv",
            db.scalars(select(RawKeystrokeEvent).order_by(RawKeystrokeEvent.id)).yield_per(5000),
            ["id", "session_id", "participant_id", "activity_type", "field_name", "sequence_no", "event_type", "key_value", "code", "timestamp_ms", "relative_time_ms", "is_backspace", "is_paste", "is_focus_event", "created_at"],
        ),
        (
            "baselines.csv",
            db.scalars(select(Baseline).order_by(Baseline.id)).all(),
            ["id", "participant_id", "name", "version", "activity_scope", "session_ids_json", "baseline_json", "is_active", "created_at"],
        ),
        (
            "evaluation_runs.csv",
            db.scalars(select(EvaluationRun).order_by(EvaluationRun.id)).all(),
            ["id", "name", "baseline_id", "activity_scope", "test_session_ids_json", "config_json", "summary_json", "created_at"],
        ),
        (
            "evaluation_results.csv",
            db.scalars(select(EvaluationResult).order_by(EvaluationResult.id)).all(),
            ["id", "evaluation_run_id", "test_session_id", "baseline_participant_id", "test_participant_id", "expected_label", "engine_results_json", "decision_json", "created_at"],
        ),
    ]
    for filename, rows, columns in definitions:
        _write_csv(temp_dir / filename, rows, columns)

    readme = temp_dir / "README.txt"
    readme.write_text(
        "Behavioral DNA Study export\n\n"
        "participant_devices.csv deliberately excludes authentication token hashes.\n"
        "Metric vectors and engine details are JSON-encoded in their respective CSV columns.\n"
        "Flight time uses UD timing and may be negative when keystrokes overlap.\n",
        encoding="utf-8",
    )

    zip_path = Path(tempfile.mkstemp(prefix="behavioral_dna_export_", suffix=".zip")[1])
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in temp_dir.iterdir():
            archive.write(file_path, arcname=file_path.name)
    for file_path in temp_dir.iterdir():
        file_path.unlink(missing_ok=True)
    temp_dir.rmdir()
    return zip_path
