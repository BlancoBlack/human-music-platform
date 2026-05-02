"""
Append-only listening checkpoints (hybrid ingestion).

Checkpoints are not ListeningEvents: they do not affect validate_listen, payouts,
or weights. Final POST /stream remains the economic source of truth.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import Session

# Allowed POST /stream/start-session source_type values (persisted on ListeningSession).
ALLOWED_LISTENING_SESSION_SOURCE_TYPES = frozenset(
    ("playlist", "discovery", "search", "direct")
)
DEFAULT_LISTENING_SESSION_SOURCE_TYPE = "direct"
_MAX_SOURCE_ID_LEN = 128

from app.models.listening_event import ListeningEvent
from app.models.listening_session import ListeningSession
from app.models.listening_session_checkpoint import ListeningSessionCheckpoint
from app.models.song import Song
from app.models.user import User

logger = logging.getLogger(__name__)


def _checkpoint_idle_timedelta() -> timedelta:
    raw = (os.getenv("LISTENING_SESSION_CHECKPOINT_IDLE_MINUTES") or "").strip()
    try:
        minutes = int(raw) if raw else 20
    except ValueError:
        minutes = 20
    return timedelta(minutes=max(1, min(minutes, 24 * 60)))


def _normalize_optional_source(
    *,
    source_type: str | None,
    source_id: str | None,
) -> tuple[str | None, str | None]:
    st = str(source_type).strip() if source_type is not None else None
    if st == "":
        st = None
    sid = str(source_id).strip() if source_id is not None else None
    if sid == "":
        sid = None
    return st, sid


def process_start_listening_session(
    db: Session,
    *,
    user_id: int,
    song_id: int,
    discovery_request_id: str | None = None,
    discovery_section: str | None = None,
    discovery_position: int | None = None,
    source_type: str | None = None,
    source_id: str | None = None,
) -> Dict[str, Any]:
    """Create a listening session bound to one song (hybrid player)."""
    norm_type, norm_id = _normalize_optional_source(
        source_type=source_type, source_id=source_id
    )
    if norm_id is not None and norm_type is None:
        raise HTTPException(
            status_code=400,
            detail="source_id requires source_type",
        )
    if norm_type is not None and norm_type not in ALLOWED_LISTENING_SESSION_SOURCE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid source_type; allowed: "
                + ", ".join(sorted(ALLOWED_LISTENING_SESSION_SOURCE_TYPES))
            ),
        )
    if norm_id is not None and len(norm_id) > _MAX_SOURCE_ID_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"source_id must be at most {_MAX_SOURCE_ID_LEN} characters",
        )

    if norm_type is None:
        norm_type = DEFAULT_LISTENING_SESSION_SOURCE_TYPE
        norm_id = None

    if (
        db.query(Song.id)
        .filter(Song.id == song_id, Song.deleted_at.is_(None))
        .first()
        is None
    ):
        raise HTTPException(status_code=404, detail="Song not found")
    if db.query(User.id).filter(User.id == user_id).first() is None:
        raise HTTPException(status_code=404, detail="User not found")

    session = ListeningSession(
        user_id=user_id,
        song_id=song_id,
        discovery_request_id=discovery_request_id,
        discovery_section=discovery_section,
        discovery_position=discovery_position,
        source_type=norm_type,
        source_id=norm_id,
    )
    db.add(session)
    logger.info(
        "listening_session_flush_started",
        extra={
            "user_id": user_id,
            "song_id": song_id,
            "discovery_request_id": discovery_request_id,
            "discovery_section": discovery_section,
            "discovery_position": discovery_position,
            "source_type": norm_type,
            "source_id": norm_id,
        },
    )
    try:
        db.flush()
        logger.info(
            "listening_session_flush_succeeded",
            extra={
                "user_id": user_id,
                "song_id": song_id,
                "session_id": session.id,
                "discovery_request_id": discovery_request_id,
                "discovery_section": discovery_section,
                "discovery_position": discovery_position,
                "source_type": norm_type,
                "source_id": norm_id,
            },
        )

        # Refresh only after the ORM instance is persistent and has a PK.
        if session.id is None:
            raise RuntimeError("Listening session id was not generated after flush")
        if not inspect(session).persistent:
            raise RuntimeError("Listening session is not persistent after flush")

        db.refresh(session)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception(
            "listening_session_creation_failed",
            extra={
                "user_id": user_id,
                "song_id": song_id,
                "discovery_request_id": discovery_request_id,
                "discovery_section": discovery_section,
                "discovery_position": discovery_position,
                "source_type": norm_type,
                "source_id": norm_id,
            },
        )
        raise
    logger.info(
        "listening_session_started",
        extra={
            "user_id": user_id,
            "song_id": song_id,
            "session_id": session.id,
            "discovery_request_id": discovery_request_id,
            "discovery_section": discovery_section,
            "discovery_position": discovery_position,
            "source_type": norm_type,
            "source_id": norm_id,
        },
    )
    return {"session_id": session.id}


def process_stream_checkpoint(
    db: Session,
    *,
    user_id: int,
    session_id: int,
    song_id: int,
    sequence: int,
    position_seconds: int,
) -> Dict[str, Any]:
    """
    Record a checkpoint for an active, non-finalized listening session.

    The first checkpoint for a session must use sequence 0; after that each new
    sequence must be strictly greater than the current max (monotonic).
    Exact duplicate (session_id, sequence) is idempotent: returns the existing
    row (safe for network retries).
    """
    if sequence < 0:
        raise HTTPException(status_code=400, detail="sequence must be >= 0")
    if position_seconds < 0:
        raise HTTPException(status_code=400, detail="position_seconds must be >= 0")

    if (
        db.query(Song.id)
        .filter(Song.id == song_id, Song.deleted_at.is_(None))
        .first()
        is None
    ):
        raise HTTPException(status_code=404, detail="Song not found")

    session = (
        db.query(ListeningSession).filter(ListeningSession.id == session_id).first()
    )
    if session is None or int(session.user_id) != int(user_id):
        raise HTTPException(status_code=404, detail="Listening session not found")

    if session.finalized_at is not None:
        raise HTTPException(
            status_code=409,
            detail="Listening session is finalized",
        )

    if (
        db.query(ListeningEvent.id)
        .filter(ListeningEvent.session_id == session_id)
        .limit(1)
        .first()
        is not None
    ):
        raise HTTPException(
            status_code=409,
            detail="Listening session is finalized",
        )

    if session.song_id is None:
        session.song_id = song_id
    elif int(session.song_id) != int(song_id):
        raise HTTPException(
            status_code=409,
            detail="song_id does not match this listening session",
        )

    now = datetime.utcnow()
    last_cp_at = (
        db.query(func.max(ListeningSessionCheckpoint.created_at))
        .filter(ListeningSessionCheckpoint.session_id == session_id)
        .scalar()
    )
    idle_ref = last_cp_at or session.started_at or now
    if now - idle_ref > _checkpoint_idle_timedelta():
        raise HTTPException(
            status_code=410,
            detail={
                "error": "session_expired",
                "message": "Listening session expired (no checkpoint within idle window)",
            },
        )

    last_sequence = (
        db.query(func.max(ListeningSessionCheckpoint.sequence))
        .filter(ListeningSessionCheckpoint.session_id == session_id)
        .scalar()
    )

    existing_same_seq = (
        db.query(ListeningSessionCheckpoint)
        .filter(
            ListeningSessionCheckpoint.session_id == session_id,
            ListeningSessionCheckpoint.sequence == sequence,
        )
        .first()
    )
    if existing_same_seq is not None:
        if int(existing_same_seq.user_id) != int(user_id):
            raise HTTPException(
                status_code=409,
                detail="checkpoint sequence already recorded for another user",
            )
        if int(existing_same_seq.song_id) != int(song_id):
            raise HTTPException(
                status_code=409,
                detail="checkpoint sequence already recorded with a different song_id",
            )
        logger.info(
            "stream_checkpoint_duplicate",
            extra={
                "user_id": user_id,
                "session_id": session_id,
                "song_id": song_id,
                "sequence": sequence,
                "checkpoint_id": existing_same_seq.id,
            },
        )
        return {
            "status": "duplicate",
            "checkpoint_id": existing_same_seq.id,
            "session_id": session_id,
        }

    if last_sequence is None and sequence != 0:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "invalid_sequence_start",
                "message": "First checkpoint must have sequence 0",
            },
        )

    if last_sequence is not None and sequence < int(last_sequence):
        raise HTTPException(
            status_code=409,
            detail="sequence must be greater than the last checkpoint for this session",
        )

    row = ListeningSessionCheckpoint(
        session_id=session_id,
        user_id=user_id,
        song_id=song_id,
        sequence=sequence,
        position_seconds=position_seconds,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        again = (
            db.query(ListeningSessionCheckpoint)
            .filter(
                ListeningSessionCheckpoint.session_id == session_id,
                ListeningSessionCheckpoint.sequence == sequence,
            )
            .first()
        )
        if again is not None:
            if int(again.user_id) != int(user_id) or int(again.song_id) != int(
                song_id
            ):
                raise HTTPException(
                    status_code=409,
                    detail="checkpoint sequence conflict",
                ) from None
            logger.info(
                "stream_checkpoint_duplicate_race",
                extra={
                    "user_id": user_id,
                    "session_id": session_id,
                    "song_id": song_id,
                    "sequence": sequence,
                    "checkpoint_id": again.id,
                },
            )
            return {
                "status": "duplicate",
                "checkpoint_id": again.id,
                "session_id": session_id,
            }
        raise HTTPException(
            status_code=409,
            detail="checkpoint sequence conflict",
        ) from None

    db.refresh(row)
    logger.info(
        "stream_checkpoint_created",
        extra={
            "user_id": user_id,
            "session_id": session_id,
            "song_id": song_id,
            "sequence": sequence,
            "checkpoint_id": row.id,
        },
    )
    return {
        "status": "ok",
        "checkpoint_id": row.id,
        "session_id": session_id,
    }
