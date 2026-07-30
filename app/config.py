from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
EXPORT_DIR = BASE_DIR / "exports"
DATA_DIR.mkdir(parents=True, exist_ok=True)
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

APP_NAME = os.getenv("APP_NAME", "Behavioral DNA Continuous Authentication Study")
APP_ENV = os.getenv("APP_ENV", "development").lower()
SECRET_KEY = os.getenv("SECRET_KEY", "development-only-change-this-secret")
RESEARCHER_PASSWORD = os.getenv("RESEARCHER_PASSWORD", "change-me")
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'behavioral_dna_study.db'}")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://") and "+psycopg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

TARGET_SESSIONS = int(os.getenv("TARGET_SESSIONS", "10"))
CONSENT_VERSION = os.getenv("CONSENT_VERSION", "1.0")
STUDY_CONTACT = os.getenv("STUDY_CONTACT", "the research team")
STORE_KEY_VALUES = os.getenv("STORE_KEY_VALUES", "false").lower() in {"1", "true", "yes"}
RESEARCHER_SESSION_HOURS = int(os.getenv("RESEARCHER_SESSION_HOURS", "12"))

FIXED_TEXT = (
    "Continuous authentication is increasingly important in remote, hybrid, and shared computing "
    "environments where a valid login does not guarantee that the original user remains the active "
    "session operator. This study presents Behavioral DNA, an explainable continuous authentication "
    "framework that uses keystroke dynamics, behavioral profiling, and multi-engine statistical "
    "verification to detect suspicious deviations during an active session."
)
FREE_PROMPT_1 = "In one complete sentence, describe your country."
FREE_PROMPT_2 = "In 2-3 complete sentences, explain why you love your country."

METRICS = [
    "hold_time",
    "flight_time",
    "digraph_latency",
    "trigraph_latency",
    "typing_speed",
    "error_rate",
    "pause_pattern",
    "consistency_score",
]

METRIC_LABELS = {
    "hold_time": "Hold Time",
    "flight_time": "Flight Time",
    "digraph_latency": "Digraph Latency",
    "trigraph_latency": "Trigraph Latency",
    "typing_speed": "Typing Speed",
    "error_rate": "Error Rate",
    "pause_pattern": "Pause Pattern",
    "consistency_score": "Consistency Score",
}

DEFAULT_ENGINE_CONFIG = {
    "active_engines": {
        "z_score": True,
        "envelope": True,
        "mahalanobis": True,
        "drift": True,
    },
    "fusion_method": "median",
    "majority_cutoff": 70.0,
    "weights": {
        "z_score": 1.0,
        "envelope": 1.0,
        "mahalanobis": 1.0,
        "drift": 1.0,
    },
    "thresholds": {
        "genuine": 85.0,
        "genuine_min": 70.0,
        "monitor": 70.0,
        "monitor_min": 45.0,
        "step_up": 55.0,
        "lock_override": 25.0,
    },
}
