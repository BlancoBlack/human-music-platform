import logging
import time
import uuid
from datetime import datetime
from types import SimpleNamespace
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.database import engine
from app.core.queue import queue
from app.models.ingestion_lock import IngestionLock
from app.models.listening_event import ListeningEvent
from app.models.listening_session import ListeningSession
from app.models.song import Song
from app.models.user import User
from app.services.listening_validation import validate_listen
from app.workers.listen_worker import process_listening_event

logger = logging.getLogger(__name__)

_IDEMPOTENCY_KEY_MAX_LEN = 128
_CORRELATION_ID_MAX_LEN = 64


def _resolve_correlation_id(raw: Optional[str]) -> str:
    if raw is None:
        return uuid.uuid4().hex
    s = raw.strip()
    if not s:
        return uuid.uuid4().hex
    if len(s) > _CORRELATION_ID_MAX_LEN:
        return s[:_CORRELATION_ID_MAX_LEN]
    return s


def _normalize_idempotency_key(key: Optional[str]) -> Optional[str]:
    if key is None:
        return None
    s = key.strip()
    if not s:
        return None
    if len(s) > _IDEMPOTENCY_KEY_MAX_LEN:
        return s[:_IDEMPOTENCY_KEY_MAX_LEN]
    return s


# -----------------------------------------------------------------------------
# TODO: Multi-DB ingestion serialization (SQLite vs PostgreSQL)
#
# Current behavior (SQLite only): `_acquire_ingestion_lock_sqlite` upserts
# `ingestion_locks` so writers block per (user_id, song_id) until the prior
# transaction commits—then `validate_listen` + `ListeningEvent` insert see
# up-to-date rows. Non-SQLite dialects log `ingestion_lock_skipped_*` and do
# NOT serialize (unsafe for production if multiple writers hit Postgres).
#
# When adding PostgreSQL support, explicitly branch on `engine.dialect.name`
# (e.g. `"sqlite"` vs `"postgresql"`) and replace the lock-table upsert with a
# mechanism that is *equivalent* in scope and duration:
#
#   Option A — Row lock on `ingestion_locks`:
#     - In the same transaction as validate+insert: ensure a row exists for
#       (user_id, song_id), then `SELECT … FROM ingestion_locks WHERE … FOR UPDATE`
#       (or ORM equivalent with `with_for_update()`), so only one session
#       proceeds per pair until commit/rollback.
#
#   Option B — Transaction-scoped advisory lock:
#     - e.g. `pg_advisory_xact_lock(...)` keyed by a stable hash of
#       (user_id, song_id), released automatically at transaction end—same
#       mutual exclusion as today without relying on SQLite’s writer mutex.
#
# Requirements for any implementation:
#   - Lock must be acquired *before* `validate_listen` and held until
#     `ListeningEvent` is committed (same ordering as now).
#   - Keep idempotency duplicate short-circuit *before* locking (no change).
#   - Preserve structured logs (`ingestion_lock_wait`, `ingestion_lock_retry`,
#     `ingestion_lock_acquired`) or map them to PG lock-wait / retries so
#     observability stays comparable.
#   - Re-verify concurrent integration tests: two parallel requests for the same
#     (user_id, song_id) must not both pass antifraud as *valid* due to TOCTOU.
#
# Do not remove the SQLite path when adding Postgres; keep behavior equivalent.
# -----------------------------------------------------------------------------


def _acquire_ingestion_lock_sqlite(
    db: Session, *, user_id: int, song_id: int, correlation_id: str
) -> None:
    """Upsert lock row so SQLite serializes writers per (user_id, song_id)."""
    tbl = IngestionLock.__table__
    max_attempts = 3
    delays_sec = (0.05, 0.075, 0.1)

    for attempt in range(1, max_attempts + 1):
        if attempt > 1:
            logger.info(
                "ingestion_lock_retry",
                extra={
                    "correlation_id": correlation_id,
                    "user_id": user_id,
                    "song_id": song_id,
                    "attempt": attempt,
                },
            )
            time.sleep(delays_sec[attempt - 1])
        else:
            logger.info(
                "ingestion_lock_wait",
                extra={
                    "correlation_id": correlation_id,
                    "user_id": user_id,
                    "song_id": song_id,
                },
            )

        try:
            now = datetime.utcnow()
            ins = sqlite_insert(tbl).values(
                user_id=user_id, song_id=song_id, locked_at=now
            )
            stmt = ins.on_conflict_do_update(
                index_elements=[tbl.c.user_id, tbl.c.song_id],
                set_={"locked_at": ins.excluded.locked_at},
            )
            db.execute(stmt)
            db.flush()
            logger.info(
                "ingestion_lock_acquired",
                extra={
                    "correlation_id": correlation_id,
                    "user_id": user_id,
                    "song_id": song_id,
                },
            )
            return
        except OperationalError as exc:
            msg = str(exc).lower()
            if "database is locked" not in msg and "database table is locked" not in msg:
                raise
            if attempt >= max_attempts:
                raise HTTPException(
                    status_code=503,
                    detail="Database temporarily unavailable",
                ) from exc


def _acquire_ingestion_lock(
    db: Session, *, user_id: int, song_id: int, correlation_id: str
) -> None:
    """
    Serialize validate_listen + insert per (user_id, song_id).

    See module TODO above: SQLite uses `ingestion_locks` upsert; PostgreSQL
    must use FOR UPDATE or advisory locks with equivalent semantics— not
    implemented yet.
    """
    if engine.dialect.name == "sqlite":
        _acquire_ingestion_lock_sqlite(
            db, user_id=user_id, song_id=song_id, correlation_id=correlation_id
        )
    else:
        # TODO: implement PostgreSQL branch (FOR UPDATE or advisory lock); until
        # then ingestion is not serialized on this dialect.
        logger.warning(
            "ingestion_lock_skipped_unsupported_dialect",
            extra={
                "correlation_id": correlation_id,
                "user_id": user_id,
                "song_id": song_id,
                "dialect": engine.dialect.name,
            },
        )


class StreamService:
    def process_stream(
        self,
        db: Session,
        user_id: Optional[int],
        song_id: int,
        duration: int,
        *,
        listening_session_id: Optional[int] = None,
        idempotency_key: Optional[str] = None,
        event_timestamp: Optional[datetime] = None,
        correlation_id: Optional[str] = None,
    ) -> dict:
        key = _normalize_idempotency_key(idempotency_key)
        cid = _resolve_correlation_id(correlation_id)

        logger.info(
            "stream_request_received",
            extra={
                "correlation_id": cid,
                "user_id": user_id,
                "song_id": song_id,
                "duration": duration,
                "idempotency_key": key,
                "listening_session_id": listening_session_id,
            },
        )

        def response(
            *,
            status: str,
            event_id: Optional[int],
            listening_session_id: Optional[int],
            is_valid: bool,
            validation_reason: Optional[str],
        ) -> dict:
            return {
                "status": status,
                "event_id": event_id,
                "listening_session_id": listening_session_id,
                "is_valid": is_valid,
                "validation_reason": validation_reason,
            }

        if user_id is None:
            raise HTTPException(status_code=400, detail="user_id is required")

        if key is not None:
            existing = (
                db.query(ListeningEvent)
                .filter(
                    ListeningEvent.user_id == user_id,
                    ListeningEvent.idempotency_key == key,
                )
                .first()
            )
            if existing is not None:
                logger.info(
                    "stream_duplicate_detected",
                    extra={
                        "correlation_id": cid,
                        "user_id": user_id,
                        "song_id": song_id,
                        "idempotency_key": key,
                        "event_id": existing.id,
                    },
                )
                return response(
                    status="duplicate",
                    event_id=existing.id,
                    listening_session_id=existing.session_id,
                    is_valid=bool(existing.is_valid),
                    validation_reason=existing.validation_reason,
                )

        if db.query(User.id).filter(User.id == user_id).first() is None:
            raise HTTPException(status_code=404, detail="User not found")

        if duration < 5:
            logger.info(
                "stream_ignored_short",
                extra={
                    "correlation_id": cid,
                    "user_id": user_id,
                    "song_id": song_id,
                    "duration": duration,
                },
            )
            return response(
                status="ignored",
                event_id=None,
                listening_session_id=None,
                is_valid=False,
                validation_reason="short_listen",
            )

        session: ListeningSession | None = None
        if listening_session_id is not None:
            session = (
                db.query(ListeningSession)
                .filter(ListeningSession.id == listening_session_id)
                .first()
            )
            if session is None or int(session.user_id) != int(user_id):
                raise HTTPException(
                    status_code=404,
                    detail="Listening session not found",
                )

        _acquire_ingestion_lock(db, user_id=user_id, song_id=song_id, correlation_id=cid)

        if session is None:
            session = ListeningSession(user_id=user_id)
            db.add(session)
            db.flush()

        song = db.query(Song).filter(Song.id == song_id).first()
        song_for_validation = song if song is not None else SimpleNamespace(id=song_id)
        now_utc = datetime.utcnow()
        validation = validate_listen(
            user_id=user_id,
            song=song_for_validation,
            raw_duration=duration,
            db=db,
            now_utc=now_utc,
        )

        event = ListeningEvent(
            user_id=user_id,
            song_id=song_id,
            session_id=session.id,
            duration=duration,
            is_valid=validation["is_valid"],
            validated_duration=validation["validated_duration"],
            weight=validation["weight"],
            validation_reason=validation["validation_reason"],
            idempotency_key=key,
            correlation_id=cid,
        )
        if event_timestamp is not None:
            event.timestamp = event_timestamp
            event.created_at = event_timestamp

        db.add(event)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            if key is not None:
                existing = (
                    db.query(ListeningEvent)
                    .filter(
                        ListeningEvent.user_id == user_id,
                        ListeningEvent.idempotency_key == key,
                    )
                    .first()
                )
                if existing is not None:
                    logger.info(
                        "stream_duplicate_detected",
                        extra={
                            "correlation_id": cid,
                            "user_id": user_id,
                            "song_id": song_id,
                            "idempotency_key": key,
                            "event_id": existing.id,
                        },
                    )
                    return response(
                        status="duplicate",
                        event_id=existing.id,
                        listening_session_id=existing.session_id,
                        is_valid=bool(existing.is_valid),
                        validation_reason=existing.validation_reason,
                    )
            raise

        db.refresh(event)

        logger.info(
            "stream_event_created",
            extra={
                "correlation_id": cid,
                "event_id": event.id,
                "user_id": user_id,
                "song_id": song_id,
                "session_id": session.id,
                "is_valid": validation["is_valid"],
                "validated_duration": validation["validated_duration"],
                "weight": validation["weight"],
            },
        )

        queue.enqueue(process_listening_event, event.id)

        return response(
            status="ok",
            event_id=event.id,
            listening_session_id=session.id,
            is_valid=bool(validation["is_valid"]),
            validation_reason=validation["validation_reason"],
        )
