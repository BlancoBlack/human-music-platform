"""
DB-appropriate lock when moving a payout batch to ``processing``.

- PostgreSQL: ``SELECT ... FOR UPDATE`` in a short transaction, then commit.
- SQLite (and other non-Postgres dialects): single atomic ``UPDATE ... WHERE status = ?``
  so only one session can flip the row (``rowcount`` must be 1).

Detection uses ``engine.dialect.name`` from the live SQLAlchemy engine (same source
as ``DATABASE_URL`` / default SQLite path in ``app.core.database``).
"""

from __future__ import annotations

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.database import engine
from app.models.payout_batch import PayoutBatch

LOCK_CONTENTION_MESSAGE = "Batch is currently being processed by another admin"


class BatchLockContentionError(Exception):
    """Lost lock race or batch already ``processing``; maps to HTTP 409."""


def database_dialect() -> str:
    """Return SQLAlchemy dialect name, e.g. ``postgresql``, ``sqlite``."""
    return str(engine.dialect.name)


def is_postgresql() -> bool:
    return database_dialect() == "postgresql"


def is_sqlite() -> bool:
    return database_dialect() == "sqlite"


def acquire_settle_processing_lock(db: Session, batch_id: int) -> None:
    """
    Atomically transition ``finalized`` / ``posted`` → ``processing``.

    Raises ``BatchLockContentionError`` if another worker holds ``processing``.
    Raises ``RuntimeError`` if status is invalid for settlement (non-contention).
    """
    bid = int(batch_id)
    if is_postgresql():
        batch = (
            db.query(PayoutBatch)
            .filter(PayoutBatch.id == bid)
            .with_for_update()
            .one_or_none()
        )
        if batch is None:
            db.rollback()
            raise ValueError(f"payout_batches not found batch_id={batch_id}")
        if batch.status == "processing":
            db.rollback()
            raise BatchLockContentionError(LOCK_CONTENTION_MESSAGE)
        if batch.status not in ("finalized", "posted"):
            db.rollback()
            raise RuntimeError(
                f"Settlement requires batch status finalized or posted, "
                f"got {batch.status!r}"
            )
        batch.status = "processing"
        db.add(batch)
        db.commit()
        return

    res = db.execute(
        update(PayoutBatch)
        .where(
            PayoutBatch.id == bid,
            PayoutBatch.status.in_(("finalized", "posted")),
        )
        .values(status="processing")
    )
    if res.rowcount != 1:
        db.rollback()
        cur = db.query(PayoutBatch).filter(PayoutBatch.id == bid).one_or_none()
        if cur is None:
            raise ValueError(f"payout_batches not found batch_id={batch_id}")
        if cur.status == "processing":
            raise BatchLockContentionError(LOCK_CONTENTION_MESSAGE)
        raise RuntimeError(
            f"Could not lock batch for settlement (concurrent update or invalid "
            f"status {cur.status!r})"
        )
    db.commit()


def acquire_retry_processing_lock(db: Session, batch_id: int) -> None:
    """
    Atomically transition ``failed`` → ``processing``.

    Raises ``BatchLockContentionError`` if another worker holds ``processing``.
    Raises ``RuntimeError`` if status is not ``failed`` (non-contention).
    """
    bid = int(batch_id)
    if is_postgresql():
        batch = (
            db.query(PayoutBatch)
            .filter(PayoutBatch.id == bid)
            .with_for_update()
            .one_or_none()
        )
        if batch is None:
            db.rollback()
            raise ValueError(f"payout_batches not found batch_id={batch_id}")
        if batch.status == "processing":
            db.rollback()
            raise BatchLockContentionError(LOCK_CONTENTION_MESSAGE)
        if batch.status != "failed":
            db.rollback()
            raise RuntimeError(
                f"Retry requires payout batch status 'failed', got {batch.status!r}"
            )
        batch.status = "processing"
        db.add(batch)
        db.commit()
        return

    res = db.execute(
        update(PayoutBatch)
        .where(
            PayoutBatch.id == bid,
            PayoutBatch.status == "failed",
        )
        .values(status="processing")
    )
    if res.rowcount != 1:
        db.rollback()
        cur = db.query(PayoutBatch).filter(PayoutBatch.id == bid).one_or_none()
        if cur is None:
            raise ValueError(f"payout_batches not found batch_id={batch_id}")
        if cur.status == "processing":
            raise BatchLockContentionError(LOCK_CONTENTION_MESSAGE)
        raise RuntimeError(
            f"Retry requires payout batch status 'failed', got {cur.status!r}"
        )
    db.commit()
