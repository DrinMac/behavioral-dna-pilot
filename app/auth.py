from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import RESEARCHER_SESSION_HOURS, SECRET_KEY
from .database import Participant, ParticipantDevice, get_db, utc_now


def random_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def pin_hash(pin: str) -> str:
    return hmac.new(SECRET_KEY.encode(), pin.encode(), hashlib.sha256).hexdigest()


def verify_pin(pin: str, expected_hash: str) -> bool:
    return hmac.compare_digest(pin_hash(pin), expected_hash)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def create_researcher_token() -> str:
    payload = {"role": "researcher", "exp": int(time.time()) + RESEARCHER_SESSION_HOURS * 3600}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64(hmac.new(SECRET_KEY.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify_researcher_token(token: str | None) -> bool:
    if not token or "." not in token:
        return False
    body, sig = token.split(".", 1)
    expected = _b64(hmac.new(SECRET_KEY.encode(), body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        return False
    try:
        payload = json.loads(_unb64(body))
        return payload.get("role") == "researcher" and int(payload.get("exp", 0)) > int(time.time())
    except Exception:
        return False


def require_researcher(bd_researcher: str | None = Cookie(default=None)) -> bool:
    if not verify_researcher_token(bd_researcher):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Researcher login required")
    return True


def require_participant(
    x_participant_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Participant:
    if not x_participant_token:
        raise HTTPException(status_code=401, detail="Participant token required")
    hashed = token_hash(x_participant_token)
    device = db.scalar(
        select(ParticipantDevice).where(
            ParticipantDevice.token_hash == hashed,
            ParticipantDevice.revoked.is_(False),
        )
    )
    if not device:
        raise HTTPException(status_code=401, detail="Participant session is no longer valid")
    participant = db.get(Participant, device.participant_id)
    if not participant or participant.status != "active":
        raise HTTPException(status_code=401, detail="Participant is inactive")
    device.last_seen_at = utc_now()
    participant.last_seen_at = utc_now()
    db.commit()
    return participant
