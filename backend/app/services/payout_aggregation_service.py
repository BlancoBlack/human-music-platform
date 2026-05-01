"""
Canonical artist payout aggregation for Ledger V2.

Single source of truth for artist payout buckets:
- paid: settlement.execution_status == 'confirmed'
- failed: settlement.execution_status == 'failed'
- pending: payout_batches.status == 'calculating'
- accrued: payout_batches.status in ('finalized', 'posted')
           and settlement.execution_status not in ('confirmed', 'failed')
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.explorer_urls import lora_transaction_explorer_url
from app.models.artist import Artist
from app.models.payout_batch import PayoutBatch
from app.models.payout_line import PayoutLine
from app.models.payout_settlement import PayoutSettlement


def _coerce_status(value: Optional[str]) -> str:
    return str(value or "").strip().lower()


def _is_paid(execution_status: str) -> bool:
    return execution_status == "confirmed"


def _is_failed(execution_status: str) -> bool:
    return execution_status == "failed"


def _is_pending(batch_status: str) -> bool:
    return batch_status == "calculating"


def _is_accrued(batch_status: str, execution_status: str) -> bool:
    if batch_status not in ("finalized", "posted"):
        return False
    return execution_status not in ("confirmed", "failed")


def _history_status(batch_status: str, execution_status: str) -> str:
    if _is_failed(execution_status):
        return "failed"
    if _is_paid(execution_status):
        return "paid"
    # History contract is intentionally compact: paid | pending | failed.
    if _is_pending(batch_status) or _is_accrued(batch_status, execution_status):
        return "pending"
    return "pending"


def get_artist_payout_summary_with_db(db: Session, artist_id: int) -> dict[str, Any]:
    rows = (
        db.query(
            PayoutLine.batch_id.label("batch_id"),
            PayoutBatch.period_end_at.label("period_end_at"),
            PayoutBatch.status.label("batch_status"),
            func.coalesce(func.sum(PayoutLine.amount_cents), 0).label("amount_cents"),
            PayoutSettlement.execution_status.label("execution_status"),
        )
        .join(PayoutBatch, PayoutBatch.id == PayoutLine.batch_id)
        .outerjoin(
            PayoutSettlement,
            (PayoutSettlement.batch_id == PayoutLine.batch_id)
            & (PayoutSettlement.artist_id == PayoutLine.artist_id),
        )
        .filter(PayoutLine.artist_id == int(artist_id))
        .group_by(
            PayoutLine.batch_id,
            PayoutBatch.period_end_at,
            PayoutBatch.status,
            PayoutSettlement.execution_status,
        )
        .all()
    )

    paid_cents = 0
    failed_cents = 0
    pending_cents = 0
    accrued_cents = 0
    batch_count = 0
    last_batch_date: datetime | None = None

    for row in rows:
        amount_cents = int(row.amount_cents or 0)
        batch_status = _coerce_status(row.batch_status)
        execution_status = _coerce_status(row.execution_status)

        batch_count += 1
        period_end_at = row.period_end_at
        if period_end_at is not None and (
            last_batch_date is None or period_end_at > last_batch_date
        ):
            last_batch_date = period_end_at

        # Canonical precedence prevents accidental double counting on malformed rows.
        if _is_failed(execution_status):
            failed_cents += amount_cents
            continue
        if _is_paid(execution_status):
            paid_cents += amount_cents
            continue
        if _is_pending(batch_status):
            pending_cents += amount_cents
            continue
        if _is_accrued(batch_status, execution_status):
            accrued_cents += amount_cents

    return {
        "paid_cents": int(paid_cents),
        "accrued_cents": int(accrued_cents),
        "pending_cents": int(pending_cents),
        "failed_cents": int(failed_cents),
        "batch_count": int(batch_count),
        "last_batch_date": last_batch_date,
    }


def get_artist_payout_summary(artist_id: int) -> dict[str, Any]:
    db = SessionLocal()
    try:
        return get_artist_payout_summary_with_db(db, int(artist_id))
    finally:
        db.close()


def get_artist_payout_history_with_db(
    db: Session, artist_id: int
) -> list[dict[str, Any]]:
    rows = (
        db.query(
            PayoutLine.batch_id.label("batch_id"),
            PayoutBatch.period_end_at.label("period_end_at"),
            PayoutBatch.status.label("batch_status"),
            func.coalesce(func.sum(PayoutLine.amount_cents), 0).label("amount_cents"),
            func.count(func.distinct(PayoutLine.user_id)).label("distinct_users"),
            PayoutSettlement.execution_status.label("execution_status"),
            PayoutSettlement.algorand_tx_id.label("algorand_tx_id"),
        )
        .join(PayoutBatch, PayoutBatch.id == PayoutLine.batch_id)
        .outerjoin(
            PayoutSettlement,
            (PayoutSettlement.batch_id == PayoutLine.batch_id)
            & (PayoutSettlement.artist_id == PayoutLine.artist_id),
        )
        .filter(PayoutLine.artist_id == int(artist_id))
        .group_by(
            PayoutLine.batch_id,
            PayoutBatch.period_end_at,
            PayoutBatch.status,
            PayoutSettlement.execution_status,
            PayoutSettlement.algorand_tx_id,
        )
        .order_by(PayoutBatch.period_end_at.desc(), PayoutLine.batch_id.desc())
        .all()
    )

    out: list[dict[str, Any]] = []
    for row in rows:
        batch_status = _coerce_status(row.batch_status)
        execution_status = _coerce_status(row.execution_status)
        raw_tx = getattr(row, "algorand_tx_id", None)
        tx_id: str | None = (
            str(raw_tx).strip()
            if raw_tx is not None and str(raw_tx).strip()
            else None
        )
        explorer_url = lora_transaction_explorer_url(tx_id)
        out.append(
            {
                "batch_id": int(row.batch_id),
                "date": row.period_end_at,
                "amount_cents": int(row.amount_cents or 0),
                "status": _history_status(batch_status, execution_status),
                "batch_status": batch_status,
                "distinct_users": int(row.distinct_users or 0),
                "tx_id": tx_id,
                "explorer_url": explorer_url,
            }
        )
    return out


def get_artist_payout_history(artist_id: int) -> list[dict[str, Any]]:
    db = SessionLocal()
    try:
        return get_artist_payout_history_with_db(db, int(artist_id))
    finally:
        db.close()


def get_artist_payout_capabilities_with_db(
    db: Session, artist_id: int
) -> dict[str, Any]:
    artist = db.query(Artist).filter(Artist.id == int(artist_id)).first()
    if artist is None:
        raise ValueError("Artist not found")

    selected = _coerce_status(artist.payout_method) or "none"
    supports_onchain = selected in ("crypto", "wallet")
    requires_manual = selected == "bank"
    wallet = (artist.payout_wallet_address or "").strip() or None
    bank_configured = bool((artist.payout_bank_info or "").strip())

    return {
        "payout_method_selected": selected,
        "supports_onchain_settlement": bool(supports_onchain),
        "requires_manual_settlement": bool(requires_manual),
        "wallet_address": wallet,
        "bank_configured": bool(bank_configured),
    }


def get_artist_payout_capabilities(artist_id: int) -> dict[str, Any]:
    db = SessionLocal()
    try:
        return get_artist_payout_capabilities_with_db(db, int(artist_id))
    finally:
        db.close()
