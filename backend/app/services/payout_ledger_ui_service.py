"""
Read paths for artist/admin payout UIs backed by ``payout_lines``, ``payout_batches``,
and optional ``payout_settlements`` (on-chain status).

UI labels:
- ``paid`` — settlement ``execution_status == confirmed`` (funds sent on-chain).
- ``accrued`` — batch ``finalized`` / ``posted`` but not yet confirmed on-chain.
- ``pending`` — batch ``calculating``.
- ``processing`` — batch ``draft``.
- ``failed`` — settlement row exists with ``execution_status == failed``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Sequence, Tuple

from sqlalchemy import and_, exists, func, not_
from sqlalchemy.orm import Session

from app.models.artist import Artist
from app.models.payout_batch import PayoutBatch
from app.models.payout_line import PayoutLine
from app.models.payout_settlement import PayoutSettlement


def map_ledger_ui_status(
    batch_status: Optional[str],
    settlement_execution_status: Optional[str],
) -> str:
    ex = (settlement_execution_status or "").strip().lower()
    b = (batch_status or "").strip().lower()
    if b == "calculating":
        return "pending"
    if ex == "confirmed":
        return "paid"
    if ex == "failed":
        return "failed"
    if ex in ("pending", "submitted"):
        return "accrued"
    if b in ("finalized", "posted"):
        return "accrued"
    if b == "draft":
        return "processing"
    return "processing"


def map_batch_status_to_ui(batch_status: Optional[str]) -> str:
    """Deprecated: use ``map_ledger_ui_status`` with settlement status when available."""
    return map_ledger_ui_status(batch_status, None)


@dataclass(frozen=True)
class ArtistBatchPayoutRow:
    batch_id: int
    period_end_at: Optional[datetime]
    batch_status: str
    amount_cents: int
    distinct_users: int
    ui_status: str


def artist_ledger_bucket_cents(db: Session, artist_id: int) -> Tuple[int, int, int]:
    """
    Returns (paid_cents, accrued_cents, pending_cents).
    paid = on-chain confirmed settlement; accrued = finalized/posted not confirmed;
    pending = batch calculating.
    """
    paid = (
        db.query(func.coalesce(func.sum(PayoutLine.amount_cents), 0))
        .join(
            PayoutSettlement,
            and_(
                PayoutSettlement.batch_id == PayoutLine.batch_id,
                PayoutSettlement.artist_id == PayoutLine.artist_id,
                PayoutSettlement.execution_status == "confirmed",
            ),
        )
        .filter(PayoutLine.artist_id == int(artist_id))
        .scalar()
        or 0
    )
    accrued = (
        db.query(func.coalesce(func.sum(PayoutLine.amount_cents), 0))
        .join(PayoutBatch, PayoutBatch.id == PayoutLine.batch_id)
        .outerjoin(
            PayoutSettlement,
            and_(
                PayoutSettlement.batch_id == PayoutLine.batch_id,
                PayoutSettlement.artist_id == PayoutLine.artist_id,
            ),
        )
        .filter(PayoutLine.artist_id == int(artist_id))
        .filter(PayoutBatch.status.in_(("finalized", "posted")))
        .filter(
            (PayoutSettlement.id.is_(None))
            | (
                PayoutSettlement.execution_status.notin_(("confirmed", "failed"))
            )
        )
        .scalar()
        or 0
    )
    pending = (
        db.query(func.coalesce(func.sum(PayoutLine.amount_cents), 0))
        .join(PayoutBatch, PayoutBatch.id == PayoutLine.batch_id)
        .filter(PayoutLine.artist_id == int(artist_id))
        .filter(PayoutBatch.status == "calculating")
        .scalar()
        or 0
    )
    return int(paid), int(accrued), int(pending)


def artist_paid_pending_cents(db: Session, artist_id: int) -> Tuple[int, int]:
    """Backward-compatible: returns (paid_cents, pending_cents); pending excludes accrued."""
    paid, _accrued, pending = artist_ledger_bucket_cents(db, artist_id)
    return paid, pending


def artist_batch_history(db: Session, artist_id: int) -> List[ArtistBatchPayoutRow]:
    rows = (
        db.query(
            PayoutBatch.id,
            PayoutBatch.period_end_at,
            PayoutBatch.status,
            func.coalesce(func.sum(PayoutLine.amount_cents), 0).label("cents"),
            func.count(func.distinct(PayoutLine.user_id)).label("n_users"),
        )
        .join(PayoutBatch, PayoutBatch.id == PayoutLine.batch_id)
        .filter(PayoutLine.artist_id == int(artist_id))
        .group_by(
            PayoutBatch.id,
            PayoutBatch.period_end_at,
            PayoutBatch.status,
        )
        .order_by(PayoutBatch.period_end_at.desc(), PayoutBatch.id.desc())
        .all()
    )
    bids = [int(r[0]) for r in rows]
    settlement_by_batch: dict[int, PayoutSettlement] = {}
    if bids:
        for s in (
            db.query(PayoutSettlement)
            .filter(
                PayoutSettlement.artist_id == int(artist_id),
                PayoutSettlement.batch_id.in_(bids),
            )
            .all()
        ):
            settlement_by_batch[int(s.batch_id)] = s

    out: List[ArtistBatchPayoutRow] = []
    for bid, pend_at, st, cents, n_users in rows:
        ps = settlement_by_batch.get(int(bid))
        ex = ps.execution_status if ps else None
        ui = map_ledger_ui_status(str(st or ""), ex)
        out.append(
            ArtistBatchPayoutRow(
                batch_id=int(bid),
                period_end_at=pend_at,
                batch_status=str(st or ""),
                amount_cents=int(cents or 0),
                distinct_users=int(n_users or 0),
                ui_status=ui,
            )
        )
    return out


def admin_ledger_group_counts(db: Session) -> Tuple[int, int, int, int, int, int]:
    """
    Returns (total, pending, processing, accrued, paid, failed).
    """
    rows = (
        db.query(PayoutLine.batch_id, PayoutLine.artist_id, PayoutBatch.status)
        .join(PayoutBatch, PayoutBatch.id == PayoutLine.batch_id)
        .group_by(PayoutLine.batch_id, PayoutLine.artist_id, PayoutBatch.status)
        .all()
    )
    bids = list({int(r[0]) for r in rows})
    sm: dict[Tuple[int, int], PayoutSettlement] = {}
    if bids:
        for s in db.query(PayoutSettlement).filter(PayoutSettlement.batch_id.in_(bids)).all():
            sm[(int(s.batch_id), int(s.artist_id))] = s

    total = len(rows)
    pending = processing = accrued = paid = failed = 0
    for bid, aid, st in rows:
        key = (int(bid), int(aid))
        ps = sm.get(key)
        ex = ps.execution_status if ps else None
        ui = map_ledger_ui_status(str(st or ""), ex)
        if ui == "paid":
            paid += 1
        elif ui == "accrued":
            accrued += 1
        elif ui == "pending":
            pending += 1
        elif ui == "processing":
            processing += 1
        elif ui == "failed":
            failed += 1
    return total, pending, processing, accrued, paid, failed


@dataclass(frozen=True)
class AdminLedgerGroupRow:
    batch_id: int
    artist_id: int
    batch_status: str
    period_end_at: Optional[datetime]
    created_at: Optional[datetime]
    amount_cents: int
    distinct_users: int
    artist_name: Optional[str]
    destination_wallet: Optional[str]
    ui_status: str
    algorand_tx_id: Optional[str]
    attempt_count: Optional[int]
    failure_reason: Optional[str]


def _admin_ledger_base_query(db: Session):
    return (
        db.query(
            PayoutLine.batch_id,
            PayoutLine.artist_id,
            PayoutBatch.status,
            PayoutBatch.period_end_at,
            PayoutBatch.created_at,
            func.coalesce(func.sum(PayoutLine.amount_cents), 0).label("cents"),
            func.count(func.distinct(PayoutLine.user_id)).label("n_users"),
        )
        .join(PayoutBatch, PayoutBatch.id == PayoutLine.batch_id)
        .group_by(
            PayoutLine.batch_id,
            PayoutLine.artist_id,
            PayoutBatch.status,
            PayoutBatch.period_end_at,
            PayoutBatch.created_at,
        )
    )


def _confirmed_settlement_exists():
    return exists().where(
        and_(
            PayoutSettlement.batch_id == PayoutLine.batch_id,
            PayoutSettlement.artist_id == PayoutLine.artist_id,
            PayoutSettlement.execution_status == "confirmed",
        )
    )


def _failed_settlement_exists():
    return exists().where(
        and_(
            PayoutSettlement.batch_id == PayoutLine.batch_id,
            PayoutSettlement.artist_id == PayoutLine.artist_id,
            PayoutSettlement.execution_status == "failed",
        )
    )


def fetch_admin_ledger_groups(
    db: Session,
    *,
    status: Optional[str] = None,
    artist_id: Optional[int] = None,
    artist_ids_from_name: Optional[Sequence[int]] = None,
    limit: int = 50,
) -> List[AdminLedgerGroupRow]:
    q = _admin_ledger_base_query(db)
    if artist_id is not None and artist_ids_from_name is not None:
        ids_set = set(int(x) for x in artist_ids_from_name)
        if int(artist_id) not in ids_set:
            return []
    if artist_id is not None:
        q = q.filter(PayoutLine.artist_id == int(artist_id))
    elif artist_ids_from_name is not None:
        ids = list(artist_ids_from_name)
        if not ids:
            return []
        q = q.filter(PayoutLine.artist_id.in_(ids))

    if status and str(status).strip():
        low = str(status).strip().lower()
        if low == "pending":
            q = q.filter(PayoutBatch.status == "calculating")
        elif low == "paid":
            q = q.filter(_confirmed_settlement_exists())
        elif low == "accrued":
            q = q.filter(PayoutBatch.status.in_(("finalized", "posted")))
            q = q.filter(not_(_confirmed_settlement_exists()))
            q = q.filter(not_(_failed_settlement_exists()))
        elif low == "processing":
            q = q.filter(PayoutBatch.status == "draft")
        elif low == "failed":
            q = q.filter(_failed_settlement_exists())

    rows = (
        q.order_by(
            PayoutBatch.period_end_at.desc(),
            PayoutLine.batch_id.desc(),
            PayoutLine.artist_id.asc(),
        )
        .limit(int(limit))
        .all()
    )

    keys = [(int(r[0]), int(r[1])) for r in rows]
    sm: dict[Tuple[int, int], PayoutSettlement] = {}
    if keys:
        batch_ids = list({k[0] for k in keys})
        artist_ids = list({k[1] for k in keys})
        for s in (
            db.query(PayoutSettlement)
            .filter(PayoutSettlement.batch_id.in_(batch_ids))
            .filter(PayoutSettlement.artist_id.in_(artist_ids))
            .all()
        ):
            sm[(int(s.batch_id), int(s.artist_id))] = s

    artist_ids_u = list({int(r[1]) for r in rows})
    artist_map: dict[int, Tuple[Optional[str], Optional[str]]] = {}
    if artist_ids_u:
        for a in (
            db.query(Artist.id, Artist.name, Artist.payout_wallet_address)
            .filter(Artist.id.in_(artist_ids_u))
            .all()
        ):
            artist_map[int(a.id)] = (a.name, a.payout_wallet_address)

    out: List[AdminLedgerGroupRow] = []
    for batch_id, aid, st, pend_at, created_at, cents, n_users in rows:
        name, wallet = artist_map.get(int(aid), (None, None))
        ps = sm.get((int(batch_id), int(aid)))
        ex = ps.execution_status if ps else None
        ui = map_ledger_ui_status(str(st or ""), ex)
        tx = ps.algorand_tx_id if ps else None
        attempts = int(ps.attempt_count) if (ps and ps.attempt_count is not None) else None
        failure = ps.failure_reason if ps else None
        out.append(
            AdminLedgerGroupRow(
                batch_id=int(batch_id),
                artist_id=int(aid),
                batch_status=str(st or ""),
                period_end_at=pend_at,
                created_at=created_at,
                amount_cents=int(cents or 0),
                distinct_users=int(n_users or 0),
                artist_name=name,
                destination_wallet=wallet,
                ui_status=ui,
                algorand_tx_id=tx,
                attempt_count=attempts,
                failure_reason=failure,
            )
        )
    return out


def synthetic_ledger_group_id(batch_id: int, artist_id: int) -> int:
    """Stable int id for JSON/API (batch + artist composite)."""
    return int(batch_id) * 1_000_000 + int(artist_id)
