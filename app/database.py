from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Generator

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from .config import DATABASE_URL


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def loads(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


class Base(DeclarativeBase):
    pass


class Participant(Base):
    __tablename__ = "participants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    participant_code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    recovery_pin_hash: Mapped[str] = mapped_column(String(128))
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(50), nullable=True)
    occupation: Mapped[str | None] = mapped_column(String(200), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    province: Mapped[str | None] = mapped_column(String(120), nullable=True)
    education: Mapped[str | None] = mapped_column(String(120), nullable=True)
    consent_accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_version: Mapped[str] = mapped_column(String(30), default="1.0")
    profile_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(30), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    devices: Mapped[list["ParticipantDevice"]] = relationship(back_populates="participant", cascade="all, delete-orphan")
    sessions: Mapped[list["StudySession"]] = relationship(back_populates="participant", cascade="all, delete-orphan")


class ParticipantDevice(Base):
    __tablename__ = "participant_devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    browser: Mapped[str | None] = mapped_column(String(120), nullable=True)
    os: Mapped[str | None] = mapped_column(String(120), nullable=True)
    device_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)

    participant: Mapped[Participant] = relationship(back_populates="devices")


class StudySession(Base):
    __tablename__ = "study_sessions"
    __table_args__ = (UniqueConstraint("participant_id", "session_number", name="uq_participant_session_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id", ondelete="CASCADE"), index=True)
    session_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    browser: Mapped[str | None] = mapped_column(String(120), nullable=True)
    os: Mapped[str | None] = mapped_column(String(120), nullable=True)
    device_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    keyboard_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    fixed_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    free_text_1: Mapped[str | None] = mapped_column(Text, nullable=True)
    free_text_2: Mapped[str | None] = mapped_column(Text, nullable=True)
    fixed_match_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    participant: Mapped[Participant] = relationship(back_populates="sessions")
    events: Mapped[list["RawKeystrokeEvent"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    vectors: Mapped[list["MetricVector"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class RawKeystrokeEvent(Base):
    __tablename__ = "raw_keystroke_events"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("study_sessions.id", ondelete="CASCADE"), index=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id", ondelete="CASCADE"), index=True)
    activity_type: Mapped[str] = mapped_column(String(30), index=True)
    field_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sequence_no: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(30))
    key_value: Mapped[str | None] = mapped_column(String(80), nullable=True)
    code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    timestamp_ms: Mapped[float] = mapped_column(Float)
    relative_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_backspace: Mapped[bool] = mapped_column(Boolean, default=False)
    is_paste: Mapped[bool] = mapped_column(Boolean, default=False)
    is_focus_event: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    session: Mapped[StudySession] = relationship(back_populates="events")


class MetricVector(Base):
    __tablename__ = "metric_vectors"
    __table_args__ = (UniqueConstraint("session_id", "activity_type", name="uq_session_activity_vector"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("study_sessions.id", ondelete="CASCADE"), index=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id", ondelete="CASCADE"), index=True)
    activity_type: Mapped[str] = mapped_column(String(30), index=True)
    vector_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    session: Mapped[StudySession] = relationship(back_populates="vectors")


class Baseline(Base):
    __tablename__ = "baselines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    version: Mapped[int] = mapped_column(Integer, default=1)
    activity_scope: Mapped[str] = mapped_column(String(30), default="combined")
    session_ids_json: Mapped[str] = mapped_column(Text)
    baseline_json: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(180))
    baseline_id: Mapped[int] = mapped_column(ForeignKey("baselines.id", ondelete="CASCADE"), index=True)
    activity_scope: Mapped[str] = mapped_column(String(30), default="combined")
    test_session_ids_json: Mapped[str] = mapped_column(Text)
    config_json: Mapped[str] = mapped_column(Text)
    summary_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class EvaluationResult(Base):
    __tablename__ = "evaluation_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evaluation_run_id: Mapped[int] = mapped_column(ForeignKey("evaluation_runs.id", ondelete="CASCADE"), index=True)
    test_session_id: Mapped[int] = mapped_column(ForeignKey("study_sessions.id", ondelete="CASCADE"), index=True)
    baseline_participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id"), index=True)
    test_participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id"), index=True)
    expected_label: Mapped[str] = mapped_column(String(20))
    engine_results_json: Mapped[str] = mapped_column(Text)
    decision_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(60), index=True)
    area: Mapped[str] = mapped_column(String(60), index=True)
    message: Mapped[str] = mapped_column(Text)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


engine_kwargs: dict[str, Any] = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
engine = create_engine(DATABASE_URL, **engine_kwargs)

if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _sqlite_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def log_event(db: Session, event_type: str, area: str, message: str, details: Any = None) -> None:
    db.add(AuditLog(event_type=event_type, area=area, message=message, details_json=dumps(details or {})))
