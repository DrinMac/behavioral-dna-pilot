from __future__ import annotations

import copy
import hashlib
import secrets
import string
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.background import BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .auth import (
    create_researcher_token,
    pin_hash,
    random_token,
    require_participant,
    require_researcher,
    token_hash,
    verify_pin,
)
from .baseline import build_baseline
from .config import (
    APP_ENV,
    APP_NAME,
    CONSENT_VERSION,
    DEFAULT_ENGINE_CONFIG,
    FIXED_TEXT,
    FREE_PROMPT_1,
    FREE_PROMPT_2,
    METRIC_LABELS,
    METRICS,
    RESEARCHER_PASSWORD,
    STORE_KEY_VALUES,
    STUDY_CONTACT,
    TARGET_SESSIONS,
)
from .database import (
    Baseline,
    EvaluationResult,
    EvaluationRun,
    MetricVector,
    Participant,
    ParticipantDevice,
    RawKeystrokeEvent,
    StudySession,
    dumps,
    get_db,
    init_db,
    loads,
    log_event,
    utc_now,
)
from .decision import make_decision
from .engines import run_engines
from .evaluation import compute_evaluation_metrics
from .exporter import build_export_zip
from .features import extract_features

app = FastAPI(title=APP_NAME, version="4.2")
init_db()

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class DeviceInfo(BaseModel):
    browser: str = "Unknown"
    os: str = "Unknown"
    device_type: str = "Unknown"
    keyboard_type: str = "Unknown"


class ReserveIn(BaseModel):
    consent_accepted: bool
    device: DeviceInfo | None = None


class RegistrationIn(BaseModel):
    age: int = Field(ge=18, le=100)
    gender: str = Field(min_length=1, max_length=50)
    occupation: str = Field(min_length=1, max_length=200)
    city: str = Field(min_length=1, max_length=120)
    province: str = Field(min_length=1, max_length=120)
    education: str = Field(min_length=1, max_length=120)
    device: DeviceInfo


class RestoreIn(BaseModel):
    participant_code: str
    recovery_pin: str
    device: DeviceInfo | None = None


class StartSessionIn(BaseModel):
    device: DeviceInfo


class EventIn(BaseModel):
    sequence_no: int
    event_type: str
    key: str | None = None
    code: str | None = None
    timestamp_ms: float
    relative_time_ms: float | None = None
    field_name: str | None = None
    segment: str | None = None
    is_backspace: bool = False
    is_paste: bool = False
    is_focus_event: bool = False
    repeat: bool = False


class AnalyzeSessionIn(BaseModel):
    device: DeviceInfo
    initial_text: str = ""
    fixed_text: str
    free_text_1: str
    free_text_2: str
    initial_events: list[EventIn] = Field(default_factory=list)
    fixed_events: list[EventIn]
    free_events: list[EventIn]


class ResearcherLoginIn(BaseModel):
    password: str


class BaselineIn(BaseModel):
    participant_id: int
    session_ids: list[int]
    activity_scope: Literal["initial", "fixed", "free", "combined"] = "combined"
    name: str = ""


class EvaluationIn(BaseModel):
    baseline_id: int
    test_session_ids: list[int]
    activity_scope: Literal["initial", "fixed", "free", "combined"] = "combined"
    name: str = ""
    config: dict[str, Any] = Field(default_factory=lambda: copy.deepcopy(DEFAULT_ENGINE_CONFIG))
    label_overrides: dict[str, Literal["genuine", "impostor"]] = Field(default_factory=dict)
    allow_baseline_overlap: bool = False


def _iso(value: Any) -> str | None:
    return value.isoformat() if value else None


def _participant_code(db: Session) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    for _ in range(50):
        code = "DNA-" + "".join(secrets.choice(alphabet) for _ in range(5))
        if not db.scalar(select(Participant.id).where(Participant.participant_code == code)):
            return code
    raise RuntimeError("Could not generate a unique participant code")


def _session_code() -> str:
    return "SES-" + secrets.token_hex(8).upper()


def _new_device(db: Session, participant: Participant, token: str, device: DeviceInfo | None) -> ParticipantDevice:
    metadata = device or DeviceInfo()
    row = ParticipantDevice(
        participant_id=participant.id,
        token_hash=token_hash(token),
        browser=metadata.browser,
        os=metadata.os,
        device_type=metadata.device_type,
    )
    db.add(row)
    return row


def _participant_payload(db: Session, participant: Participant) -> dict[str, Any]:
    sessions = db.scalars(
        select(StudySession).where(StudySession.participant_id == participant.id).order_by(StudySession.session_number)
    ).all()
    completed = sum(1 for item in sessions if item.status == "completed")
    session_payloads = []
    for item in sessions:
        session_payloads.append(
            {
                "id": item.id,
                "session_code": item.session_code,
                "session_number": item.session_number,
                "status": item.status,
                "browser": item.browser,
                "os": item.os,
                "device_type": item.device_type,
                "keyboard_type": item.keyboard_type,
                "started_at": _iso(item.started_at),
                "completed_at": _iso(item.completed_at),
            }
        )
    active = next((item for item in reversed(session_payloads) if item["status"] in {"draft", "analyzed"}), None)
    return {
        "participant": {
            "id": participant.id,
            "participant_code": participant.participant_code,
            "profile_completed": participant.profile_completed,
            "age": participant.age,
            "gender": participant.gender,
            "occupation": participant.occupation,
            "city": participant.city,
            "province": participant.province,
            "education": participant.education,
        },
        "sessions": session_payloads,
        "active_session": active,
        "completed_sessions": completed,
        "target_sessions": TARGET_SESSIONS,
        "can_start_new_session": participant.profile_completed and active is None and completed < TARGET_SESSIONS,
        "study_complete": completed >= TARGET_SESSIONS,
    }


def _metric_payload(db: Session, session_id: int) -> dict[str, Any]:
    rows = db.scalars(select(MetricVector).where(MetricVector.session_id == session_id)).all()
    return {row.activity_type: loads(row.vector_json, {}) for row in rows}


def _event_dict(event: EventIn, activity_type: str) -> dict[str, Any]:
    item = event.model_dump()
    item["activity_type"] = activity_type
    item["segment"] = item.get("segment") or f"{activity_type}:{item.get('field_name') or 'main'}"
    return item


def _sanitize_key_value(event: EventIn) -> str | None:
    key = event.key
    if not key:
        return None
    if STORE_KEY_VALUES or len(key) > 1:
        return key[:80]
    return None


def _sanitize_code(event: EventIn) -> str | None:
    code = event.code
    if not code or STORE_KEY_VALUES:
        return code
    if code.startswith("Key"):
        return "CharacterKey"
    if code.startswith(("Digit", "Numpad")):
        return "DigitKey"
    if code in {"Space", "Backspace", "Delete", "Enter", "Tab", "ShiftLeft", "ShiftRight"}:
        return code
    return "OtherKey"


def _normalize_engine_config(config: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(DEFAULT_ENGINE_CONFIG)
    merged["active_engines"].update(config.get("active_engines", {}))
    merged["weights"].update(config.get("weights", {}))
    merged["thresholds"].update(config.get("thresholds", {}))
    if config.get("fusion_method") in {"mean", "median", "minimum", "weighted", "majority"}:
        merged["fusion_method"] = config["fusion_method"]
    if "majority_cutoff" in config:
        merged["majority_cutoff"] = float(config["majority_cutoff"])
    return merged


@app.get("/")
def participant_page() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "participant.html",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )


@app.get("/researcher")
def researcher_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "researcher.html")


@app.get("/api/health")
def health(db: Session = Depends(get_db)) -> dict[str, Any]:
    return {
        "status": "ok",
        "participants": db.scalar(select(func.count()).select_from(Participant)) or 0,
        "sessions": db.scalar(select(func.count()).select_from(StudySession)) or 0,
    }


@app.get("/api/public/config")
def public_config() -> dict[str, Any]:
    return {
        "app_name": APP_NAME,
        "target_sessions": TARGET_SESSIONS,
        "consent_version": CONSENT_VERSION,
        "study_contact": STUDY_CONTACT,
        "fixed_text": FIXED_TEXT,
        "free_prompt_1": FREE_PROMPT_1,
        "free_prompt_2": FREE_PROMPT_2,
        "metrics": METRICS,
        "metric_labels": METRIC_LABELS,
        "privacy": {
            "precise_geolocation_collected": False,
            "ip_address_intentionally_stored": False,
            "key_values_stored": STORE_KEY_VALUES,
        },
    }


@app.post("/api/participants/reserve")
def reserve_participant(payload: ReserveIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    if not payload.consent_accepted:
        raise HTTPException(400, "Consent is required to participate")
    code = _participant_code(db)
    recovery_pin = f"{secrets.randbelow(1_000_000):06d}"
    participant = Participant(
        participant_code=code,
        recovery_pin_hash=pin_hash(recovery_pin),
        consent_accepted=True,
        consent_version=CONSENT_VERSION,
    )
    db.add(participant)
    db.flush()
    token = random_token()
    _new_device(db, participant, token, payload.device)
    session = StudySession(participant_id=participant.id, session_code=_session_code(), session_number=1, status="draft")
    db.add(session)
    log_event(db, "PARTICIPANT_RESERVED", "participant", f"Reserved {code}", {"participant_id": participant.id})
    db.commit()
    return {
        "participant_code": code,
        "recovery_pin": recovery_pin,
        "participant_token": token,
        "session": {"id": session.id, "session_code": session.session_code, "session_number": 1, "status": session.status},
    }


@app.post("/api/participants/register")
def register_participant(
    payload: RegistrationIn,
    participant: Participant = Depends(require_participant),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    participant.age = payload.age
    participant.gender = payload.gender.strip()
    participant.occupation = payload.occupation.strip()
    participant.city = payload.city.strip()
    participant.province = payload.province.strip()
    participant.education = payload.education.strip()
    participant.profile_completed = True
    active = db.scalar(
        select(StudySession).where(
            StudySession.participant_id == participant.id,
            StudySession.status.in_(["draft", "analyzed"]),
        ).order_by(StudySession.session_number.desc())
    )
    if active:
        active.browser = payload.device.browser
        active.os = payload.device.os
        active.device_type = payload.device.device_type
        active.keyboard_type = payload.device.keyboard_type
    log_event(db, "PARTICIPANT_REGISTERED", "participant", f"Completed profile for {participant.participant_code}")
    db.commit()
    return _participant_payload(db, participant)


@app.post("/api/participants/restore")
def restore_participant(payload: RestoreIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    code = payload.participant_code.strip().upper()
    participant = db.scalar(select(Participant).where(Participant.participant_code == code))
    if not participant or not verify_pin(payload.recovery_pin.strip(), participant.recovery_pin_hash):
        raise HTTPException(401, "Participant ID or recovery PIN is incorrect")
    token = random_token()
    _new_device(db, participant, token, payload.device)
    participant.last_seen_at = utc_now()
    log_event(db, "PARTICIPANT_RESTORED", "participant", f"Restored {participant.participant_code}")
    db.commit()
    return {"participant_token": token, **_participant_payload(db, participant)}


@app.get("/api/participants/me")
def participant_me(
    participant: Participant = Depends(require_participant),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return _participant_payload(db, participant)


@app.post("/api/participants/sessions/start")
def start_participant_session(
    payload: StartSessionIn,
    participant: Participant = Depends(require_participant),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if not participant.profile_completed:
        raise HTTPException(400, "Complete participant registration first")
    active = db.scalar(
        select(StudySession).where(
            StudySession.participant_id == participant.id,
            StudySession.status.in_(["draft", "analyzed"]),
        )
    )
    if active:
        return {"id": active.id, "session_code": active.session_code, "session_number": active.session_number, "status": active.status}
    completed = db.scalar(
        select(func.count()).select_from(StudySession).where(
            StudySession.participant_id == participant.id,
            StudySession.status == "completed",
        )
    ) or 0
    if completed >= TARGET_SESSIONS:
        raise HTTPException(400, "The required number of study sessions has already been completed")
    highest = db.scalar(select(func.max(StudySession.session_number)).where(StudySession.participant_id == participant.id)) or 0
    session = StudySession(
        participant_id=participant.id,
        session_code=_session_code(),
        session_number=int(highest) + 1,
        status="draft",
        browser=payload.device.browser,
        os=payload.device.os,
        device_type=payload.device.device_type,
        keyboard_type=payload.device.keyboard_type,
    )
    db.add(session)
    log_event(db, "SESSION_STARTED", "participant", f"Started session {session.session_number} for {participant.participant_code}")
    db.commit()
    return {"id": session.id, "session_code": session.session_code, "session_number": session.session_number, "status": session.status}


@app.post("/api/participants/sessions/{session_id}/analyze")
def analyze_participant_session(
    session_id: int,
    payload: AnalyzeSessionIn,
    participant: Participant = Depends(require_participant),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    session = db.get(StudySession, session_id)
    if not session or session.participant_id != participant.id:
        raise HTTPException(404, "Study session not found")
    if session.status == "completed":
        raise HTTPException(400, "This session has already been submitted")
    if len(payload.fixed_events) < 20 or len(payload.free_events) < 20:
        raise HTTPException(400, "Insufficient fixed-text or free-text keystroke telemetry")

    fixed_ratio = SequenceMatcher(None, payload.fixed_text.strip(), FIXED_TEXT).ratio()
    session.browser = payload.device.browser
    session.os = payload.device.os
    session.device_type = payload.device.device_type
    session.keyboard_type = payload.device.keyboard_type
    session.fixed_text = payload.fixed_text
    session.free_text_1 = payload.free_text_1
    session.free_text_2 = payload.free_text_2
    session.fixed_match_ratio = fixed_ratio

    db.execute(delete(RawKeystrokeEvent).where(RawKeystrokeEvent.session_id == session.id))
    db.execute(delete(MetricVector).where(MetricVector.session_id == session.id))

    activity_events: dict[str, list[dict[str, Any]]] = {
        "initial": [_event_dict(event, "initial") for event in payload.initial_events],
        "fixed": [_event_dict(event, "fixed") for event in payload.fixed_events],
        "free": [_event_dict(event, "free") for event in payload.free_events],
    }
    for activity_type, events in activity_events.items():
        source_events = payload.initial_events if activity_type == "initial" else payload.fixed_events if activity_type == "fixed" else payload.free_events
        for source, event in zip(source_events, events):
            db.add(
                RawKeystrokeEvent(
                    session_id=session.id,
                    participant_id=participant.id,
                    activity_type=activity_type,
                    field_name=source.field_name,
                    sequence_no=source.sequence_no,
                    event_type=source.event_type,
                    key_value=_sanitize_key_value(source),
                    code=_sanitize_code(source),
                    timestamp_ms=source.timestamp_ms,
                    relative_time_ms=source.relative_time_ms,
                    is_backspace=source.is_backspace,
                    is_paste=source.is_paste,
                    is_focus_event=source.is_focus_event,
                )
            )

    typed_texts = {
        "initial": payload.initial_text,
        "fixed": payload.fixed_text,
        "free": f"{payload.free_text_1}\n{payload.free_text_2}".strip(),
    }
    vectors: dict[str, dict[str, Any]] = {}
    for activity_type in ("initial", "fixed", "free"):
        if activity_events[activity_type]:
            vector = extract_features(activity_events[activity_type], typed_texts[activity_type])
            vectors[activity_type] = vector
            db.add(MetricVector(session_id=session.id, participant_id=participant.id, activity_type=activity_type, vector_json=dumps(vector)))

    # Keep the longitudinal Combined vector comparable across all sessions.
    # Initial registration telemetry is reported separately and is not mixed into Combined.
    combined_events = activity_events["fixed"] + activity_events["free"]
    combined_text = "\n".join([typed_texts["fixed"], typed_texts["free"]]).strip()
    combined_vector = extract_features(combined_events, combined_text)
    vectors["combined"] = combined_vector
    db.add(MetricVector(session_id=session.id, participant_id=participant.id, activity_type="combined", vector_json=dumps(combined_vector)))

    quality = {
        "fixed_match_ratio": round(fixed_ratio, 6),
        "fixed_text_exact": payload.fixed_text.strip() == FIXED_TEXT,
        "initial_available": bool(activity_events["initial"]),
        "paste_events": int(sum(1 for events in activity_events.values() for event in events if event.get("is_paste"))),
        "warnings": sorted({warning for vector in vectors.values() for warning in vector.get("sample_warnings", [])}),
    }
    session.quality_json = dumps(quality)
    session.status = "analyzed"
    session.analyzed_at = utc_now()
    log_event(db, "SESSION_ANALYZED", "participant", f"Analyzed session {session.session_number}", {"session_id": session.id})
    db.commit()
    return {
        "session": {"id": session.id, "session_code": session.session_code, "session_number": session.session_number, "status": session.status},
        "metrics": vectors,
        "quality": quality,
    }


@app.get("/api/participants/sessions/{session_id}/metrics")
def participant_session_metrics(
    session_id: int,
    participant: Participant = Depends(require_participant),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    session = db.get(StudySession, session_id)
    if not session or session.participant_id != participant.id:
        raise HTTPException(404, "Study session not found")
    return {"metrics": _metric_payload(db, session.id), "quality": loads(session.quality_json, {})}


@app.post("/api/participants/sessions/{session_id}/submit")
def submit_participant_session(
    session_id: int,
    participant: Participant = Depends(require_participant),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    session = db.get(StudySession, session_id)
    if not session or session.participant_id != participant.id:
        raise HTTPException(404, "Study session not found")
    if session.status != "analyzed":
        raise HTTPException(400, "Review the metric results before submitting")
    session.status = "completed"
    session.completed_at = utc_now()
    log_event(db, "SESSION_COMPLETED", "participant", f"Completed session {session.session_number}", {"session_id": session.id})
    db.commit()
    return _participant_payload(db, participant)


@app.post("/api/research/login")
def researcher_login(payload: ResearcherLoginIn, response: Response) -> dict[str, bool]:
    if not secrets.compare_digest(payload.password, RESEARCHER_PASSWORD):
        raise HTTPException(401, "Incorrect researcher password")
    response.set_cookie(
        "bd_researcher",
        create_researcher_token(),
        httponly=True,
        secure=APP_ENV == "production",
        samesite="lax",
        max_age=12 * 3600,
        path="/",
    )
    return {"ok": True}


@app.post("/api/research/logout")
def researcher_logout(response: Response) -> dict[str, bool]:
    response.delete_cookie("bd_researcher", path="/")
    return {"ok": True}


@app.get("/api/research/me")
def researcher_me(_: bool = Depends(require_researcher)) -> dict[str, Any]:
    return {"authenticated": True, "app_name": APP_NAME}


@app.get("/api/research/dashboard")
def research_dashboard(_: bool = Depends(require_researcher), db: Session = Depends(get_db)) -> dict[str, Any]:
    participants = db.scalar(select(func.count()).select_from(Participant).where(Participant.profile_completed.is_(True))) or 0
    completed_sessions = db.scalar(select(func.count()).select_from(StudySession).where(StudySession.status == "completed")) or 0
    analyzed_sessions = db.scalar(select(func.count()).select_from(StudySession).where(StudySession.status == "analyzed")) or 0
    baselines = db.scalar(select(func.count()).select_from(Baseline)) or 0
    evaluation_runs = db.scalar(select(func.count()).select_from(EvaluationRun)) or 0
    completed_participants = db.scalar(
        select(func.count()).select_from(
            select(StudySession.participant_id)
            .where(StudySession.status == "completed")
            .group_by(StudySession.participant_id)
            .having(func.count(StudySession.id) >= TARGET_SESSIONS)
            .subquery()
        )
    ) or 0
    return {
        "participants": participants,
        "completed_sessions": completed_sessions,
        "analyzed_not_submitted": analyzed_sessions,
        "baselines": baselines,
        "evaluation_runs": evaluation_runs,
        "participants_reaching_target": completed_participants,
        "target_sessions": TARGET_SESSIONS,
    }


@app.get("/api/research/participants")
def research_participants(_: bool = Depends(require_researcher), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    participants = db.scalars(select(Participant).where(Participant.profile_completed.is_(True)).order_by(Participant.id)).all()
    output = []
    for participant in participants:
        completed = db.scalar(
            select(func.count()).select_from(StudySession).where(
                StudySession.participant_id == participant.id,
                StudySession.status == "completed",
            )
        ) or 0
        output.append(
            {
                "id": participant.id,
                "participant_code": participant.participant_code,
                "age": participant.age,
                "gender": participant.gender,
                "occupation": participant.occupation,
                "city": participant.city,
                "province": participant.province,
                "education": participant.education,
                "completed_sessions": completed,
                "target_sessions": TARGET_SESSIONS,
                "created_at": _iso(participant.created_at),
                "last_seen_at": _iso(participant.last_seen_at),
            }
        )
    return output


@app.get("/api/research/sessions")
def research_sessions(
    participant_id: int | None = Query(default=None),
    status: str | None = Query(default="completed"),
    _: bool = Depends(require_researcher),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    query = select(StudySession, Participant.participant_code).join(Participant, Participant.id == StudySession.participant_id)
    if participant_id is not None:
        query = query.where(StudySession.participant_id == participant_id)
    if status:
        query = query.where(StudySession.status == status)
    rows = db.execute(query.order_by(StudySession.completed_at, StudySession.id)).all()
    output = []
    for session, participant_code in rows:
        vectors = _metric_payload(db, session.id)
        output.append(
            {
                "id": session.id,
                "session_code": session.session_code,
                "participant_id": session.participant_id,
                "participant_code": participant_code,
                "session_number": session.session_number,
                "status": session.status,
                "browser": session.browser,
                "os": session.os,
                "device_type": session.device_type,
                "keyboard_type": session.keyboard_type,
                "fixed_match_ratio": session.fixed_match_ratio,
                "quality": loads(session.quality_json, {}),
                "metrics_available": sorted(vectors.keys()),
                "started_at": _iso(session.started_at),
                "completed_at": _iso(session.completed_at),
            }
        )
    return output


@app.get("/api/research/sessions/{session_id}")
def research_session_detail(
    session_id: int,
    _: bool = Depends(require_researcher),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    session = db.get(StudySession, session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    event_count = db.scalar(select(func.count()).select_from(RawKeystrokeEvent).where(RawKeystrokeEvent.session_id == session.id)) or 0
    return {
        "session": {
            "id": session.id,
            "session_code": session.session_code,
            "participant_id": session.participant_id,
            "session_number": session.session_number,
            "status": session.status,
            "browser": session.browser,
            "os": session.os,
            "device_type": session.device_type,
            "keyboard_type": session.keyboard_type,
            "fixed_text": session.fixed_text,
            "free_text_1": session.free_text_1,
            "free_text_2": session.free_text_2,
            "fixed_match_ratio": session.fixed_match_ratio,
            "quality": loads(session.quality_json, {}),
            "started_at": _iso(session.started_at),
            "completed_at": _iso(session.completed_at),
        },
        "metrics": _metric_payload(db, session.id),
        "raw_event_count": event_count,
    }


@app.post("/api/research/baselines")
def create_baseline(
    payload: BaselineIn,
    _: bool = Depends(require_researcher),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    participant = db.get(Participant, payload.participant_id)
    if not participant:
        raise HTTPException(404, "Participant not found")
    unique_ids = list(dict.fromkeys(payload.session_ids))
    if not unique_ids:
        raise HTTPException(400, "Select one or more enrollment sessions")
    sessions = db.scalars(
        select(StudySession).where(
            StudySession.id.in_(unique_ids),
            StudySession.participant_id == participant.id,
            StudySession.status == "completed",
        )
    ).all()
    if len(sessions) != len(unique_ids):
        raise HTTPException(400, "All baseline sessions must be completed sessions from the selected participant")
    vectors = db.scalars(
        select(MetricVector).where(
            MetricVector.session_id.in_(unique_ids),
            MetricVector.activity_type == payload.activity_scope,
        )
    ).all()
    if len(vectors) != len(unique_ids):
        raise HTTPException(400, f"One or more selected sessions do not contain a {payload.activity_scope} metric vector")
    baseline_data = build_baseline([loads(vector.vector_json, {}) for vector in vectors])
    version = (db.scalar(select(func.max(Baseline.version)).where(Baseline.participant_id == participant.id, Baseline.activity_scope == payload.activity_scope)) or 0) + 1
    db.execute(
        select(Baseline).where(Baseline.participant_id == participant.id, Baseline.activity_scope == payload.activity_scope)
    )
    for row in db.scalars(select(Baseline).where(Baseline.participant_id == participant.id, Baseline.activity_scope == payload.activity_scope)).all():
        row.is_active = False
    baseline = Baseline(
        participant_id=participant.id,
        name=payload.name.strip() or f"{participant.participant_code} {payload.activity_scope.title()} Baseline v{version}",
        version=version,
        activity_scope=payload.activity_scope,
        session_ids_json=dumps(unique_ids),
        baseline_json=dumps(baseline_data),
        is_active=True,
    )
    db.add(baseline)
    log_event(db, "BASELINE_CREATED", "research", baseline.name, {"session_ids": unique_ids, "scope": payload.activity_scope})
    db.commit()
    return _baseline_payload(baseline, participant.participant_code)


def _baseline_payload(row: Baseline, participant_code: str | None = None) -> dict[str, Any]:
    return {
        "id": row.id,
        "participant_id": row.participant_id,
        "participant_code": participant_code,
        "name": row.name,
        "version": row.version,
        "activity_scope": row.activity_scope,
        "session_ids": loads(row.session_ids_json, []),
        "baseline": loads(row.baseline_json, {}),
        "is_active": row.is_active,
        "created_at": _iso(row.created_at),
    }


@app.get("/api/research/baselines")
def research_baselines(_: bool = Depends(require_researcher), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.execute(
        select(Baseline, Participant.participant_code).join(Participant, Participant.id == Baseline.participant_id).order_by(Baseline.id.desc())
    ).all()
    return [_baseline_payload(baseline, participant_code) for baseline, participant_code in rows]


@app.post("/api/research/evaluations")
def create_evaluation(
    payload: EvaluationIn,
    _: bool = Depends(require_researcher),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    baseline_row = db.get(Baseline, payload.baseline_id)
    if not baseline_row:
        raise HTTPException(404, "Baseline not found")
    if payload.activity_scope != baseline_row.activity_scope:
        raise HTTPException(400, "Evaluation activity scope must match the baseline activity scope")
    test_ids = list(dict.fromkeys(payload.test_session_ids))
    baseline_session_ids = set(loads(baseline_row.session_ids_json, []))
    if not payload.allow_baseline_overlap and baseline_session_ids.intersection(test_ids):
        raise HTTPException(400, "Baseline-development sessions cannot be reused as evaluation sessions")
    if not test_ids:
        raise HTTPException(400, "Select one or more evaluation sessions")
    sessions = db.scalars(
        select(StudySession).where(StudySession.id.in_(test_ids), StudySession.status == "completed").order_by(StudySession.completed_at, StudySession.id)
    ).all()
    if len(sessions) != len(test_ids):
        raise HTTPException(400, "All evaluation sessions must be completed")
    vector_rows = db.scalars(
        select(MetricVector).where(MetricVector.session_id.in_(test_ids), MetricVector.activity_type == payload.activity_scope)
    ).all()
    vectors_by_session = {row.session_id: loads(row.vector_json, {}) for row in vector_rows}
    if len(vectors_by_session) != len(test_ids):
        raise HTTPException(400, f"One or more selected sessions do not contain a {payload.activity_scope} metric vector")

    config = _normalize_engine_config(payload.config)
    baseline_data = loads(baseline_row.baseline_json, {})
    result_rows: list[dict[str, Any]] = []
    previous_d2_by_participant: dict[int, float] = {}
    for session in sessions:
        vector = vectors_by_session[session.id]
        previous_d2 = previous_d2_by_participant.get(session.participant_id)
        engines = run_engines(vector, baseline_data, previous_d2)
        mahalanobis_d2 = float(next(result["score"] for result in engines if result["engine_name"] == "mahalanobis"))
        previous_d2_by_participant[session.participant_id] = mahalanobis_d2
        decision = make_decision(engines, config)
        decision["mahalanobis_d2"] = mahalanobis_d2
        expected = payload.label_overrides.get(str(session.id)) or ("genuine" if session.participant_id == baseline_row.participant_id else "impostor")
        result_rows.append(
            {
                "test_session_id": session.id,
                "test_session_number": session.session_number,
                "test_participant_id": session.participant_id,
                "expected_label": expected,
                "engine_results": engines,
                "decision": decision,
            }
        )

    summary = compute_evaluation_metrics(result_rows)
    run = EvaluationRun(
        name=payload.name.strip() or f"Evaluation of Baseline {baseline_row.id}",
        baseline_id=baseline_row.id,
        activity_scope=payload.activity_scope,
        test_session_ids_json=dumps(test_ids),
        config_json=dumps(config),
        summary_json=dumps(summary),
    )
    db.add(run)
    db.flush()
    for row in result_rows:
        db.add(
            EvaluationResult(
                evaluation_run_id=run.id,
                test_session_id=row["test_session_id"],
                baseline_participant_id=baseline_row.participant_id,
                test_participant_id=row["test_participant_id"],
                expected_label=row["expected_label"],
                engine_results_json=dumps(row["engine_results"]),
                decision_json=dumps(row["decision"]),
            )
        )
    log_event(db, "EVALUATION_CREATED", "research", run.name, {"baseline_id": baseline_row.id, "test_session_ids": test_ids})
    db.commit()
    return {"run": _evaluation_run_payload(run), "results": result_rows}


def _evaluation_run_payload(run: EvaluationRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "name": run.name,
        "baseline_id": run.baseline_id,
        "activity_scope": run.activity_scope,
        "test_session_ids": loads(run.test_session_ids_json, []),
        "config": loads(run.config_json, {}),
        "summary": loads(run.summary_json, {}),
        "created_at": _iso(run.created_at),
    }


@app.get("/api/research/evaluations")
def research_evaluations(_: bool = Depends(require_researcher), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.scalars(select(EvaluationRun).order_by(EvaluationRun.id.desc())).all()
    return [_evaluation_run_payload(row) for row in rows]


@app.get("/api/research/evaluations/{run_id}")
def research_evaluation_detail(
    run_id: int,
    _: bool = Depends(require_researcher),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    run = db.get(EvaluationRun, run_id)
    if not run:
        raise HTTPException(404, "Evaluation run not found")
    rows = db.execute(
        select(EvaluationResult, StudySession.session_code, StudySession.session_number, Participant.participant_code)
        .join(StudySession, StudySession.id == EvaluationResult.test_session_id)
        .join(Participant, Participant.id == EvaluationResult.test_participant_id)
        .where(EvaluationResult.evaluation_run_id == run.id)
        .order_by(EvaluationResult.id)
    ).all()
    results = []
    for result, session_code, session_number, participant_code in rows:
        results.append(
            {
                "id": result.id,
                "test_session_id": result.test_session_id,
                "session_code": session_code,
                "session_number": session_number,
                "participant_code": participant_code,
                "expected_label": result.expected_label,
                "engine_results": loads(result.engine_results_json, []),
                "decision": loads(result.decision_json, {}),
            }
        )
    return {"run": _evaluation_run_payload(run), "results": results}


@app.get("/api/research/export")
def research_export(
    background_tasks: BackgroundTasks,
    _: bool = Depends(require_researcher),
    db: Session = Depends(get_db),
) -> FileResponse:
    zip_path = build_export_zip(db)
    background_tasks.add_task(zip_path.unlink, missing_ok=True)
    return FileResponse(zip_path, filename="behavioral_dna_study_export.zip", media_type="application/zip")
