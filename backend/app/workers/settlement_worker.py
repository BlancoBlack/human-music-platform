"""
V2 settlement: one Algorand USDC transfer per (payout batch, artist).

Requires batch status finalized or posted, non-zero total_cents, artist wallet,
and batch pool conservation vs payout_lines.

Lifecycle: pending → submitted (after broadcast) → confirmed (after algod confirms).
Confirmed rows are never retried; submitted rows resume confirmation only (no resend).
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime
from typing import Callable, List, Optional

from algosdk import error as algo_error
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.blockchain.algorand_client_v2 import AlgorandClient
from app.core.database import SessionLocal
from app.models.artist import Artist
from app.models.payout_batch import PayoutBatch
from app.models.payout_settlement import PayoutSettlement
from app.services.settlement_breakdown import (
    build_payout_breakdown,
    breakdown_totals_match,
    canonical_json_bytes,
    compute_breakdown_hash,
    verify_batch_pool_conservation,
)

logger = logging.getLogger(__name__)

USDC_ASSET_ID = 10458941
MAX_ATTEMPTS = 3


def _batch_correlation_id(batch_id: int) -> str:
    return f"batch:{int(batch_id)}"


def _wait_rounds() -> int:
    return int(os.getenv("SETTLEMENT_TX_WAIT_ROUNDS", "1000"))


def _settlement_extra(
    event: str,
    *,
    batch_id: int,
    artist_id: int,
    tx_id: Optional[str] = None,
    amount_cents: Optional[int] = None,
    breakdown_hash: Optional[str] = None,
) -> dict:
    return {
        "settlement_event": event,
        "batch_id": int(batch_id),
        "artist_id": int(artist_id),
        "tx_id": tx_id,
        "amount_cents": amount_cents,
        "breakdown_hash": breakdown_hash,
    }


def _payout_lines_count_and_distinct_artist_ids(
    db: Session, batch_id: int
) -> tuple[int, List[Optional[int]]]:
    """
    Raw SQL only (no joins / line_type filter), for debugging and settlement input.

    - SELECT COUNT(*) FROM payout_lines WHERE batch_id = ?
    - SELECT DISTINCT artist_id FROM payout_lines WHERE batch_id = ?
    """
    bid = int(batch_id)
    lines_count = int(
        db.execute(
            text("SELECT COUNT(*) FROM payout_lines WHERE batch_id = :bid"),
            {"bid": bid},
        ).scalar()
        or 0
    )
    rows = db.execute(
        text("SELECT DISTINCT artist_id FROM payout_lines WHERE batch_id = :bid"),
        {"bid": bid},
    ).fetchall()
    raw_ids: List[Optional[int]] = [r[0] for r in rows]
    return lines_count, raw_ids


def _payout_settlement_stats(db: Session, batch_id: int) -> tuple[int, dict[str, int]]:
    """Total rows for batch_id and counts grouped by execution_status."""
    bid = int(batch_id)
    total = (
        db.query(func.count(PayoutSettlement.id))
        .filter(PayoutSettlement.batch_id == bid)
        .scalar()
        or 0
    )
    rows = (
        db.query(PayoutSettlement.execution_status, func.count(PayoutSettlement.id))
        .filter(PayoutSettlement.batch_id == bid)
        .group_by(PayoutSettlement.execution_status)
        .all()
    )
    dist: dict[str, int] = {}
    for status, cnt in rows:
        key = str(status or "")
        dist[key] = int(cnt or 0)
    return int(total), dist


def _already_settled_artist_ids(db: Session, batch_id: int) -> set[int]:
    """
    Artist ids with nothing left to do at batch orchestration time.

    Only ``confirmed`` is terminal. ``submitted`` must still run
    ``_resume_submitted_settlement`` (wait_for_confirmation), so it is NOT included.
    """
    rows = (
        db.query(PayoutSettlement.artist_id)
        .filter(PayoutSettlement.batch_id == int(batch_id))
        .filter(PayoutSettlement.execution_status == "confirmed")
        .all()
    )
    return {int(r[0]) for r in rows if r[0] is not None}


def process_batch_settlement(
    batch_id: int,
    *,
    db: Optional[Session] = None,
    algorand_client_factory: Optional[Callable[[], AlgorandClient]] = None,
) -> dict:
    """
    Process all artists for ``batch_id``.

    Idempotent: confirmed rows are skipped; submitted rows only wait for confirmation;
    failed rows retry up to ``MAX_ATTEMPTS`` (new broadcast).

    Returns summary dict with counts (for tests / logging).
    ``processed`` is kept equal to ``confirmed`` for backwards compatibility.
    """
    own_session = db is None
    db = db if db is not None else SessionLocal()
    skipped = 0
    confirmed = 0
    failed = 0
    try:
        logger.info("Settlement started for batch %s", int(batch_id))
        batch = db.query(PayoutBatch).filter(PayoutBatch.id == int(batch_id)).one_or_none()
        if batch is None:
            raise ValueError(f"payout_batches not found batch_id={batch_id}")
        if batch.status not in ("finalized", "posted"):
            raise RuntimeError(
                f"Settlement requires batch status finalized or posted, got {batch.status!r}"
            )
        if batch.snapshot_id is None:
            raise RuntimeError(f"batch_id={batch_id} has no snapshot_id")

        verify_batch_pool_conservation(db, int(batch_id), int(batch.snapshot_id))

        lines_count, artist_ids_raw = _payout_lines_count_and_distinct_artist_ids(
            db, int(batch_id)
        )
        logger.info(
            "Settlement debug batch=%s lines_count=%s artist_ids=%s",
            int(batch_id),
            lines_count,
            artist_ids_raw,
        )

        artist_ids = sorted({int(a) for a in artist_ids_raw if a is not None})
        if not artist_ids:
            if lines_count > 0:
                logger.error(
                    "CRITICAL: payout_lines exist but no artist_ids found for batch %s "
                    "(lines_count=%s distinct_raw=%s)",
                    int(batch_id),
                    lines_count,
                    artist_ids_raw,
                )
            else:
                logger.error(
                    "Settlement aborted: no payout_lines rows for batch %s",
                    int(batch_id),
                )
            return {
                "batch_id": int(batch_id),
                "processed": 0,
                "confirmed": 0,
                "skipped": 0,
                "failed": 0,
                "artists": 0,
            }

        logger.info(
            "Settlement batch=%s distinct_artist_count=%s proceeding",
            int(batch_id),
            len(artist_ids),
        )

        already_settled_ids = _already_settled_artist_ids(db, int(batch_id))
        target_artist_ids = [aid for aid in artist_ids if aid not in already_settled_ids]
        pre_skipped = len(already_settled_ids.intersection(set(artist_ids)))

        if pre_skipped == len(artist_ids):
            logger.info(
                "Settlement batch=%s skipped: all artists already confirmed",
                int(batch_id),
            )
            return {
                "status": "skipped",
                "reason": "batch already settled",
                "batch_id": int(batch_id),
                "processed": 0,
                "confirmed": 0,
                "skipped": pre_skipped,
                "failed": 0,
                "artists": len(artist_ids),
            }

        mnemonic_phrase = os.getenv("ALGOD_MNEMONIC")
        if algorand_client_factory is None:
            if not mnemonic_phrase:
                raise RuntimeError("ALGOD_MNEMONIC is not set; cannot settle on-chain")
            client_factory = lambda: AlgorandClient(mnemonic_phrase)
        else:
            client_factory = algorand_client_factory

        client = client_factory()

        n_before, dist_before = _payout_settlement_stats(db, int(batch_id))
        logger.info(
            "Settlement batch=%s artists_in_lines=%s payout_settlements_before=%s "
            "distribution_before=%s",
            int(batch_id),
            len(target_artist_ids),
            n_before,
            dist_before,
        )

        skipped += pre_skipped
        for artist_id in target_artist_ids:
            try:
                outcome = _settle_one_artist(
                    db,
                    batch_id=int(batch_id),
                    artist_id=int(artist_id),
                    client=client,
                )
            except Exception:
                logger.exception(
                    "Settlement artist raised batch=%s artist_id=%s",
                    int(batch_id),
                    int(artist_id),
                )
                failed += 1
                continue
            if outcome == "skipped":
                skipped += 1
            elif outcome == "confirmed":
                confirmed += 1
            elif outcome == "failed":
                failed += 1
            else:
                logger.warning(
                    "Unexpected settlement outcome batch=%s artist_id=%s outcome=%r",
                    int(batch_id),
                    int(artist_id),
                    outcome,
                )
                failed += 1

        n_after, dist_after = _payout_settlement_stats(db, int(batch_id))
        logger.info(
            "Settlement batch=%s finished payout_settlements_after=%s "
            "distribution_after=%s outcomes confirmed=%s skipped=%s failed=%s",
            int(batch_id),
            n_after,
            dist_after,
            confirmed,
            skipped,
            failed,
        )

        if pre_skipped > 0:
            status = "partial"
        else:
            status = "processed"

        return {
            "status": status,
            "batch_id": int(batch_id),
            "processed": confirmed,
            "confirmed": confirmed,
            "skipped": skipped,
            "failed": failed,
            "artists": len(artist_ids),
        }
    except Exception:
        logger.exception("Settlement failed for batch %s", int(batch_id))
        raise
    finally:
        if own_session:
            db.close()


def _resume_submitted_settlement(
    db: Session,
    row: PayoutSettlement,
    *,
    batch_id: int,
    artist_id: int,
    client: AlgorandClient,
) -> str:
    """Poll algod for an already-broadcast tx; never call send_asset."""
    if not row.algorand_tx_id:
        row.execution_status = "pending"
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.commit()
        return "skipped"

    try:
        verify_bd = build_payout_breakdown(db, batch_id, artist_id)
        verify_hash = compute_breakdown_hash(verify_bd)
        if verify_hash != row.breakdown_hash:
            row.execution_status = "failed"
            row.failure_reason = (
                "breakdown_hash drift after submit (stored vs recomputed)"
            )[:4000]
            row.attempt_count = int(row.attempt_count or 0) + 1
            row.updated_at = datetime.utcnow()
            db.add(row)
            db.commit()
            logger.error(
                "settlement_hash_drift_submitted",
                extra=_settlement_extra(
                    "hash_drift_submitted",
                    batch_id=batch_id,
                    artist_id=artist_id,
                    tx_id=row.algorand_tx_id,
                    amount_cents=row.total_cents,
                    breakdown_hash=row.breakdown_hash,
                ),
            )
            return "failed"
    except Exception as e:
        row.execution_status = "failed"
        row.failure_reason = f"resume pre-check failed: {e}"[:4000]
        row.attempt_count = int(row.attempt_count or 0) + 1
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.commit()
        logger.exception(
            "settlement_resume_precheck_failed",
            extra=_settlement_extra(
                "resume_precheck_failed",
                batch_id=batch_id,
                artist_id=artist_id,
                tx_id=row.algorand_tx_id,
                amount_cents=row.total_cents,
                breakdown_hash=row.breakdown_hash,
            ),
        )
        return "failed"

    tx_id = row.algorand_tx_id
    try:
        client.wait_for_confirmation(tx_id, wait_rounds=_wait_rounds())
    except algo_error.TransactionRejectedError as e:
        row.execution_status = "failed"
        row.failure_reason = str(e)[:4000]
        row.attempt_count = int(row.attempt_count or 0) + 1
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.commit()
        logger.exception(
            "settlement_tx_rejected_on_resume",
            extra=_settlement_extra(
                "tx_rejected_resume",
                batch_id=batch_id,
                artist_id=artist_id,
                tx_id=tx_id,
                amount_cents=row.total_cents,
                breakdown_hash=row.breakdown_hash,
            ),
        )
        return "failed"
    except algo_error.ConfirmationTimeoutError:
        logger.warning(
            "settlement_confirm_timeout_resume",
            extra=_settlement_extra(
                "confirm_timeout_resume",
                batch_id=batch_id,
                artist_id=artist_id,
                tx_id=tx_id,
                amount_cents=row.total_cents,
                breakdown_hash=row.breakdown_hash,
            ),
        )
        return "skipped"

    now = datetime.utcnow()
    row.execution_status = "confirmed"
    row.confirmed_at = now
    row.failure_reason = None
    row.updated_at = now
    db.add(row)
    db.commit()
    logger.info(
        "settlement_confirmed",
        extra=_settlement_extra(
            "confirmed",
            batch_id=batch_id,
            artist_id=artist_id,
            tx_id=tx_id,
            amount_cents=row.total_cents,
            breakdown_hash=row.breakdown_hash,
        ),
    )
    logger.info(
        "settlement_tx_success",
        extra={
            "correlation_id": _batch_correlation_id(batch_id),
            "batch_id": int(batch_id),
            "artist_id": int(artist_id),
            "tx_id": tx_id,
        },
    )
    return "confirmed"


def _settle_one_artist(
    db: Session,
    *,
    batch_id: int,
    artist_id: int,
    client: AlgorandClient,
) -> str:
    row = (
        db.query(PayoutSettlement)
        .filter(
            PayoutSettlement.batch_id == int(batch_id),
            PayoutSettlement.artist_id == int(artist_id),
        )
        .one_or_none()
    )

    if row is not None:
        if row.execution_status == "confirmed":
            logger.info(
                "Settlement artist batch=%s artist_id=%s skip=already_confirmed "
                "total_cents=%s destination_wallet=%s",
                batch_id,
                artist_id,
                row.total_cents,
                row.destination_wallet or "(none)",
            )
            return "skipped"
        if row.algorand_tx_id and row.execution_status in ("submitted", "pending"):
            logger.info(
                "Settlement artist batch=%s artist_id=%s resume=submitted_or_pending "
                "total_cents=%s destination_wallet=%s tx_id=%s",
                batch_id,
                artist_id,
                row.total_cents,
                row.destination_wallet or "(none)",
                row.algorand_tx_id,
            )
            return _resume_submitted_settlement(
                db, row, batch_id=batch_id, artist_id=artist_id, client=client
            )
        if row.execution_status == "submitted" and not row.algorand_tx_id:
            logger.warning(
                "settlement_inconsistent_submitted_no_tx",
                extra=_settlement_extra(
                    "inconsistent_submitted",
                    batch_id=batch_id,
                    artist_id=artist_id,
                    amount_cents=row.total_cents,
                    breakdown_hash=row.breakdown_hash,
                ),
            )
            row.execution_status = "pending"
            row.updated_at = datetime.utcnow()
            db.add(row)
            db.commit()
        if row.execution_status == "failed" and int(row.attempt_count or 0) >= MAX_ATTEMPTS:
            return "skipped"

    breakdown = build_payout_breakdown(db, batch_id, artist_id)
    if not breakdown_totals_match(breakdown):
        raise RuntimeError(f"breakdown song sum mismatch batch={batch_id} artist={artist_id}")

    total_cents = int(breakdown["total_cents"])
    if total_cents <= 0:
        logger.info(
            "Settlement artist batch=%s artist_id=%s skip=zero_amount total_cents=0 "
            "destination_wallet=(n/a)",
            batch_id,
            artist_id,
        )
        logger.info(
            "settlement_skip_zero",
            extra=_settlement_extra(
                "skip_zero",
                batch_id=batch_id,
                artist_id=artist_id,
                amount_cents=0,
            ),
        )
        return "skipped"

    splits_digest = str(breakdown.get("splits_digest") or "")
    b_json = canonical_json_bytes(breakdown).decode("utf-8")
    b_hash = compute_breakdown_hash(breakdown)

    artist = db.query(Artist).filter(Artist.id == int(artist_id)).one_or_none()
    if artist is None:
        raise RuntimeError(f"artist_id={artist_id} not found")

    payout_method = (artist.payout_method or "").strip().lower()
    if payout_method not in ("wallet", "crypto"):
        logger.warning(
            "Artist %s skipped due to payout_method raw=%r normalized=%r "
            "(settlement allows wallet or crypto only)",
            artist_id,
            artist.payout_method,
            payout_method if payout_method else None,
        )
        return "skipped"

    wallet = (artist.payout_wallet_address or "").strip()
    logger.info(
        "Settlement artist batch=%s artist_id=%s total_cents=%s destination_wallet=%s",
        batch_id,
        artist_id,
        total_cents,
        wallet if wallet else "(none)",
    )
    if not wallet:
        logger.warning(
            "settlement_skip_no_wallet",
            extra=_settlement_extra(
                "skip_no_wallet",
                batch_id=batch_id,
                artist_id=artist_id,
                amount_cents=total_cents,
                breakdown_hash=b_hash,
            ),
        )
        _upsert_failed_settlement(
            db,
            batch_id=batch_id,
            artist_id=artist_id,
            total_cents=total_cents,
            breakdown_json=b_json,
            breakdown_hash=b_hash,
            splits_digest=splits_digest or None,
            destination_wallet=None,
            reason="missing artist payout_wallet_address",
        )
        return "failed"

    if row is None:
        row = PayoutSettlement(
            batch_id=int(batch_id),
            artist_id=int(artist_id),
            total_cents=total_cents,
            breakdown_json=b_json,
            breakdown_hash=b_hash,
            splits_digest=splits_digest or None,
            destination_wallet=wallet,
            execution_status="pending",
            attempt_count=0,
        )
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            row = (
                db.query(PayoutSettlement)
                .filter(
                    PayoutSettlement.batch_id == int(batch_id),
                    PayoutSettlement.artist_id == int(artist_id),
                )
                .one_or_none()
            )
            if row is None:
                return "failed"
            if row.execution_status == "confirmed":
                return "skipped"
            if row.algorand_tx_id and row.execution_status in ("submitted", "pending"):
                return _resume_submitted_settlement(
                    db, row, batch_id=batch_id, artist_id=artist_id, client=client
                )
            if row.execution_status == "failed" and int(row.attempt_count or 0) >= MAX_ATTEMPTS:
                return "skipped"

    row = (
        db.query(PayoutSettlement)
        .filter(
            PayoutSettlement.batch_id == int(batch_id),
            PayoutSettlement.artist_id == int(artist_id),
        )
        .one()
    )

    if row.execution_status == "confirmed":
        return "skipped"
    if row.algorand_tx_id and row.execution_status in ("submitted", "pending"):
        return _resume_submitted_settlement(
            db, row, batch_id=batch_id, artist_id=artist_id, client=client
        )

    row.total_cents = total_cents
    row.breakdown_json = b_json
    row.breakdown_hash = b_hash
    row.splits_digest = splits_digest or None
    row.destination_wallet = wallet
    row.updated_at = datetime.utcnow()
    db.add(row)
    db.commit()

    row = (
        db.query(PayoutSettlement)
        .filter(
            PayoutSettlement.batch_id == int(batch_id),
            PayoutSettlement.artist_id == int(artist_id),
        )
        .one()
    )
    if row.execution_status == "confirmed":
        return "skipped"
    if row.algorand_tx_id and row.execution_status in ("submitted", "pending"):
        return _resume_submitted_settlement(
            db, row, batch_id=batch_id, artist_id=artist_id, client=client
        )

    verify_bd = build_payout_breakdown(db, batch_id, artist_id)
    verify_hash = compute_breakdown_hash(verify_bd)
    if verify_hash != row.breakdown_hash:
        row.attempt_count = int(row.attempt_count or 0) + 1
        row.execution_status = "failed"
        row.failure_reason = (
            "breakdown_hash immutability check failed before send (recompute != stored)"
        )[:4000]
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.commit()
        logger.error(
            "settlement_hash_mismatch_presend",
            extra=_settlement_extra(
                "hash_mismatch_presend",
                batch_id=batch_id,
                artist_id=artist_id,
                amount_cents=total_cents,
                breakdown_hash=row.breakdown_hash,
            ),
        )
        return "failed"

    dest = (row.destination_wallet or "").strip()
    if not dest:
        row.attempt_count = int(row.attempt_count or 0) + 1
        row.execution_status = "failed"
        row.failure_reason = "missing destination_wallet on settlement row"[:4000]
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.commit()
        return "failed"

    note_obj = {"a": int(artist_id), "b": int(batch_id), "h": b_hash}
    note_bytes = json.dumps(
        note_obj,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    amount_base_units = int(total_cents) * 10_000

    logger.info(
        "settlement_tx_attempt",
        extra={
            "correlation_id": _batch_correlation_id(batch_id),
            "batch_id": int(batch_id),
            "artist_id": int(artist_id),
            "amount_cents": int(total_cents),
            "destination_wallet": dest,
        },
    )
    try:
        tx_id = client.send_asset(
            dest,
            amount_base_units,
            USDC_ASSET_ID,
            note=note_bytes,
        )
    except Exception as e:
        row = (
            db.query(PayoutSettlement)
            .filter(
                PayoutSettlement.batch_id == int(batch_id),
                PayoutSettlement.artist_id == int(artist_id),
            )
            .one()
        )
        row.attempt_count = int(row.attempt_count or 0) + 1
        row.execution_status = "failed"
        row.failure_reason = str(e)[:4000]
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.commit()
        logger.error(
            "settlement_tx_failed",
            extra={
                "correlation_id": _batch_correlation_id(batch_id),
                "batch_id": int(batch_id),
                "artist_id": int(artist_id),
                "reason": str(e),
            },
            exc_info=True,
        )
        return "failed"

    logger.info("Settlement post_send_asset artist=%s tx_id=%s", artist_id, tx_id)

    now = datetime.utcnow()
    row.algorand_tx_id = tx_id
    row.execution_status = "submitted"
    row.submitted_at = now
    row.failure_reason = None
    row.updated_at = now
    db.add(row)
    db.commit()

    logger.info(
        "settlement_tx_submitted",
        extra=_settlement_extra(
            "tx_submitted",
            batch_id=batch_id,
            artist_id=artist_id,
            tx_id=tx_id,
            amount_cents=total_cents,
            breakdown_hash=b_hash,
        ),
    )

    try:
        client.wait_for_confirmation(tx_id, wait_rounds=_wait_rounds())
    except algo_error.TransactionRejectedError as e:
        row = (
            db.query(PayoutSettlement)
            .filter(
                PayoutSettlement.batch_id == int(batch_id),
                PayoutSettlement.artist_id == int(artist_id),
            )
            .one()
        )
        row.execution_status = "failed"
        row.failure_reason = str(e)[:4000]
        row.attempt_count = int(row.attempt_count or 0) + 1
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.commit()
        logger.exception(
            "settlement_tx_rejected_after_send",
            extra=_settlement_extra(
                "tx_rejected_after_send",
                batch_id=batch_id,
                artist_id=artist_id,
                tx_id=tx_id,
                amount_cents=total_cents,
                breakdown_hash=b_hash,
            ),
        )
        return "failed"
    except algo_error.ConfirmationTimeoutError:
        logger.warning(
            "settlement_confirm_timeout_after_send",
            extra=_settlement_extra(
                "confirm_timeout_after_send",
                batch_id=batch_id,
                artist_id=artist_id,
                tx_id=tx_id,
                amount_cents=total_cents,
                breakdown_hash=b_hash,
            ),
        )
        return "skipped"

    row = (
        db.query(PayoutSettlement)
        .filter(
            PayoutSettlement.batch_id == int(batch_id),
            PayoutSettlement.artist_id == int(artist_id),
        )
        .one()
    )
    cnow = datetime.utcnow()
    row.execution_status = "confirmed"
    row.confirmed_at = cnow
    row.updated_at = cnow
    db.add(row)
    db.commit()
    logger.info(
        "settlement_confirmed",
        extra=_settlement_extra(
            "confirmed",
            batch_id=batch_id,
            artist_id=artist_id,
            tx_id=tx_id,
            amount_cents=total_cents,
            breakdown_hash=b_hash,
        ),
    )
    logger.info(
        "settlement_tx_success",
        extra={
            "correlation_id": _batch_correlation_id(batch_id),
            "batch_id": int(batch_id),
            "artist_id": int(artist_id),
            "tx_id": tx_id,
        },
    )
    return "confirmed"


def _upsert_failed_settlement(
    db: Session,
    *,
    batch_id: int,
    artist_id: int,
    total_cents: int,
    breakdown_json: str,
    breakdown_hash: str,
    reason: str,
    splits_digest: Optional[str] = None,
    destination_wallet: Optional[str] = None,
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
            total_cents=total_cents,
            breakdown_json=breakdown_json,
            breakdown_hash=breakdown_hash,
            splits_digest=splits_digest,
            destination_wallet=destination_wallet,
            execution_status="failed",
            attempt_count=1,
            failure_reason=reason,
        )
        db.add(row)
    else:
        row.total_cents = total_cents
        row.breakdown_json = breakdown_json
        row.breakdown_hash = breakdown_hash
        if splits_digest is not None:
            row.splits_digest = splits_digest
        if destination_wallet is not None:
            row.destination_wallet = destination_wallet
        row.execution_status = "failed"
        row.attempt_count = int(row.attempt_count or 0) + 1
        row.failure_reason = reason
        row.updated_at = datetime.utcnow()
        db.add(row)
    db.commit()


def schedule_auto_settlement_after_finalize(
    batch_id: int,
    *,
    asynchronous: bool = True,
) -> None:
    """
    Run ``process_batch_settlement`` after finalize (idempotent worker).

    When ``asynchronous`` is True, runs in a daemon thread (non-blocking for HTTP).
    When False, runs in the caller thread (use from short-lived CLIs so work finishes
    before process exit).
    """
    bid = int(batch_id)
    logger.info("Auto settlement triggered for batch %s", bid)

    def _run() -> None:
        try:
            process_batch_settlement(bid)
        except Exception:
            logger.exception("Auto settlement failed for batch %s", bid)

    if not asynchronous:
        _run()
        return

    threading.Thread(
        target=_run,
        name=f"auto-settlement-batch-{bid}",
        daemon=True,
    ).start()
