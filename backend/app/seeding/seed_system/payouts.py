from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.artist import Artist
from app.models.listening_event import ListeningEvent
from app.models.payout_batch import PayoutBatch
from app.models.payout_line import PayoutLine
from app.models.payout_settlement import PayoutSettlement
from app.services.payout_service import get_treasury_artist
from app.services.payout_v2_snapshot_engine import generate_payout_lines
from app.services.snapshot_service import build_snapshot
from app.workers.settlement_worker import process_batch_settlement

logger = logging.getLogger(__name__)


def build_snapshot_and_payouts(
    db: Session,
    *,
    antifraud_version: str,
    policy_id: str,
) -> tuple[int, int]:
    min_ts = db.query(func.min(ListeningEvent.timestamp)).scalar()
    max_ts = db.query(func.max(ListeningEvent.timestamp)).scalar()
    if min_ts is None or max_ts is None:
        raise RuntimeError("No listening events found; cannot build payout batch.")

    period_start = min_ts - timedelta(seconds=1)
    period_end = max_ts + timedelta(seconds=1)
    batch = PayoutBatch(
        period_start_at=period_start,
        period_end_at=period_end,
        status="draft",
        currency="USD",
        calculation_version="v2",
        antifraud_version=antifraud_version,
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    batch_id = int(batch.id)

    build_snapshot(
        batch_id=batch_id,
        period_start_at=period_start,
        period_end_at=period_end,
        policy_id=policy_id,
    )
    inserted = int(
        generate_payout_lines(
            batch_id,
            auto_run_settlement=False,
            auto_settlement_async=False,
        )
    )
    _run_real_settlement_non_blocking(db, batch_id=batch_id)
    return batch_id, inserted


def validate_payouts(db: Session, *, batch_id: int) -> None:
    treasury_artist = get_treasury_artist(db)
    if treasury_artist is None:
        logger.warning("treasury entity missing before payout validation.")
        treasury_artist_id = None
    else:
        treasury_artist_id = int(treasury_artist.id)
        payout_method = (treasury_artist.payout_method or "").strip().lower()
        wallet = (treasury_artist.payout_wallet_address or "").strip()
        if not payout_method:
            logger.warning("treasury payout_method is empty before payout validation.")
        if payout_method in ("wallet", "crypto") and not wallet:
            logger.warning("treasury wallet missing for wallet/crypto payout method.")

    total_lines = int(
        db.query(func.count(PayoutLine.id))
        .filter(PayoutLine.batch_id == batch_id)
        .scalar()
        or 0
    )
    if total_lines < 1:
        raise RuntimeError("Validation failed: no payout lines generated.")

    non_zero = int(
        db.query(func.count(PayoutLine.id))
        .filter(PayoutLine.batch_id == batch_id, PayoutLine.amount_cents > 0)
        .scalar()
        or 0
    )
    if non_zero < 1:
        raise RuntimeError("Validation failed: all payout lines are zero.")

    treasury_cents = int(
        db.query(func.coalesce(func.sum(PayoutLine.amount_cents), 0))
        .filter(PayoutLine.batch_id == batch_id, PayoutLine.line_type == "treasury")
        .scalar()
        or 0
    )
    if treasury_cents <= 0:
        logger.warning(
            "treasury payout is zero - possible causes: insufficient funds, payout distribution edge case, treasury config issue"
        )

    artist_rows = (
        db.query(PayoutLine.artist_id)
        .filter(
            PayoutLine.batch_id == batch_id,
            PayoutLine.line_type == "royalty",
            PayoutLine.artist_id.isnot(None),
            PayoutLine.amount_cents > 0,
        )
        .distinct()
        .all()
    )
    if treasury_artist_id is not None:
        artist_rows = [row for row in artist_rows if int(row[0]) != treasury_artist_id]
    if len(artist_rows) < 2:
        logger.warning("payout validation found fewer than two paid non-treasury artists.")


def _run_real_settlement_non_blocking(db: Session, *, batch_id: int) -> None:
    artist_amounts = (
        db.query(PayoutLine.artist_id, func.coalesce(func.sum(PayoutLine.amount_cents), 0))
        .filter(
            PayoutLine.batch_id == int(batch_id),
            PayoutLine.line_type == "royalty",
            PayoutLine.artist_id.isnot(None),
        )
        .group_by(PayoutLine.artist_id)
        .all()
    )
    for artist_id, amount_cents in artist_amounts:
        logger.info(
            "payout_attempt_started",
            extra={
                "artist_id": int(artist_id),
                "amount": int(amount_cents or 0),
                "error_message": None,
            },
        )
    try:
        process_batch_settlement(int(batch_id), db=db)
    except Exception as exc:
        for artist_id, amount_cents in artist_amounts:
            _upsert_seed_failed_settlement(
                db,
                batch_id=int(batch_id),
                artist_id=int(artist_id),
                amount_cents=int(amount_cents or 0),
                reason=str(exc),
            )
        logger.warning(
            "payout_attempt_failed",
            extra={
                "artist_id": None,
                "amount": None,
                "error_message": str(exc),
            },
            exc_info=True,
        )

    settlements = (
        db.query(PayoutSettlement)
        .filter(PayoutSettlement.batch_id == int(batch_id))
        .order_by(PayoutSettlement.artist_id.asc())
        .all()
    )
    if not settlements and artist_amounts:
        for artist_id, amount_cents in artist_amounts:
            _upsert_seed_failed_settlement(
                db,
                batch_id=int(batch_id),
                artist_id=int(artist_id),
                amount_cents=int(amount_cents or 0),
                reason="settlement did not create payout_settlement row",
            )
        settlements = (
            db.query(PayoutSettlement)
            .filter(PayoutSettlement.batch_id == int(batch_id))
            .order_by(PayoutSettlement.artist_id.asc())
            .all()
        )
    for row in settlements:
        payload = {
            "artist_id": int(row.artist_id),
            "amount": int(row.total_cents or 0),
            "error_message": row.failure_reason,
        }
        status = (row.execution_status or "").strip().lower()
        if status == "confirmed":
            logger.info("payout_attempt_succeeded", extra=payload)
        elif status in {"failed", "pending", "submitted"}:
            logger.warning("payout_attempt_failed", extra=payload)


def _upsert_seed_failed_settlement(
    db: Session,
    *,
    batch_id: int,
    artist_id: int,
    amount_cents: int,
    reason: str,
) -> None:
    row = (
        db.query(PayoutSettlement)
        .filter(
            PayoutSettlement.batch_id == int(batch_id),
            PayoutSettlement.artist_id == int(artist_id),
        )
        .one_or_none()
    )
    if row is None:
        row = PayoutSettlement(
            batch_id=int(batch_id),
            artist_id=int(artist_id),
            total_cents=int(amount_cents),
            breakdown_json="{}",
            breakdown_hash=f"seed-failure-{batch_id}-{artist_id}",
            execution_status="failed",
            attempt_count=1,
            failure_reason=str(reason)[:4000],
        )
        db.add(row)
    else:
        row.total_cents = int(amount_cents)
        row.execution_status = "failed"
        row.attempt_count = int(row.attempt_count or 0) + 1
        row.failure_reason = str(reason)[:4000]
        db.add(row)
    db.commit()
