"""
Deterministic payout breakdown + SHA256 commitment for V2 settlement.

All monetary / unit fields in the breakdown dict are integers (cents, bps, units).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.payout_batch import PayoutBatch
from app.models.payout_input_snapshot import PayoutInputSnapshot
from app.models.payout_line import PayoutLine
from app.models.snapshot_listening_input import SnapshotListeningInput
from app.models.snapshot_user_pool import SnapshotUserPool
from app.models.song_artist_split import SongArtistSplit


def canonical_json_bytes(obj: Any) -> bytes:
    """Sorted keys at all levels, no insignificant whitespace, UTF-8."""
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def compute_breakdown_hash(breakdown: Dict[str, Any]) -> str:
    """SHA256 hex (lowercase) of canonical JSON."""
    payload = canonical_json_bytes(breakdown)
    return hashlib.sha256(payload).hexdigest()


def compute_splits_digest(songs: List[Dict[str, Any]]) -> str:
    """
    Fingerprint of per-song artist split bps at breakdown time (freeze for audit).
    Sorted by song_id; does not include cents or user attribution.
    """
    fingerprint: List[Dict[str, int]] = []
    for s in songs:
        if not isinstance(s, dict):
            continue
        fingerprint.append(
            {
                "artist_split_bps": int(s.get("artist_split_bps") or 0),
                "song_id": int(s.get("song_id") or 0),
            }
        )
    fingerprint.sort(key=lambda x: x["song_id"])
    return hashlib.sha256(canonical_json_bytes(fingerprint)).hexdigest()


def verify_batch_pool_conservation(db: Session, batch_id: int, snapshot_id: int) -> None:
    pool_sum = (
        db.query(func.coalesce(func.sum(SnapshotUserPool.user_pool_cents), 0))
        .filter(SnapshotUserPool.snapshot_id == int(snapshot_id))
        .scalar()
        or 0
    )
    line_sum = (
        db.query(func.coalesce(func.sum(PayoutLine.amount_cents), 0))
        .filter(PayoutLine.batch_id == int(batch_id))
        .scalar()
        or 0
    )
    if int(pool_sum) != int(line_sum):
        raise RuntimeError(
            f"Batch conservation failed batch_id={batch_id}: "
            f"snapshot_user_pool_sum={pool_sum} payout_lines_sum={line_sum}"
        )


def build_payout_breakdown(db: Session, batch_id: int, artist_id: int) -> Dict[str, Any]:
    batch = db.query(PayoutBatch).filter(PayoutBatch.id == int(batch_id)).one_or_none()
    if batch is None:
        raise ValueError(f"payout_batches not found batch_id={batch_id}")
    if batch.snapshot_id is None:
        raise ValueError(f"batch_id={batch_id} has no snapshot_id")

    snapshot_id = int(batch.snapshot_id)
    snap = (
        db.query(PayoutInputSnapshot)
        .filter(PayoutInputSnapshot.id == snapshot_id)
        .one_or_none()
    )
    if snap is None:
        raise ValueError(f"snapshot id={snapshot_id} not found")

    song_rows = (
        db.query(PayoutLine.song_id, func.sum(PayoutLine.amount_cents).label("cents"))
        .filter(
            PayoutLine.batch_id == int(batch_id),
            PayoutLine.artist_id == int(artist_id),
        )
        .group_by(PayoutLine.song_id)
        .order_by(PayoutLine.song_id.asc())
        .all()
    )

    songs_out: List[Dict[str, Any]] = []
    total_cents = 0

    for song_id, cents in song_rows:
        sid = int(song_id)
        c = int(cents or 0)
        total_cents += c

        user_rows = (
            db.query(PayoutLine.user_id)
            .filter(
                PayoutLine.batch_id == int(batch_id),
                PayoutLine.artist_id == int(artist_id),
                PayoutLine.song_id == sid,
            )
            .distinct()
            .order_by(PayoutLine.user_id.asc())
            .all()
        )
        contributor_ids: List[int] = sorted({int(r[0]) for r in user_rows})

        w_sum = 0
        r_sum = 0
        if contributor_ids:
            w_sum = (
                db.query(func.coalesce(func.sum(SnapshotListeningInput.qualified_units_i), 0))
                .filter(
                    SnapshotListeningInput.snapshot_id == snapshot_id,
                    SnapshotListeningInput.song_id == sid,
                    SnapshotListeningInput.user_id.in_(contributor_ids),
                )
                .scalar()
                or 0
            )
            r_sum = (
                db.query(func.coalesce(func.sum(SnapshotListeningInput.raw_units_i), 0))
                .filter(
                    SnapshotListeningInput.snapshot_id == snapshot_id,
                    SnapshotListeningInput.song_id == sid,
                    SnapshotListeningInput.user_id.in_(contributor_ids),
                )
                .scalar()
                or 0
            )

        lt_rows = (
            db.query(PayoutLine.line_type)
            .filter(
                PayoutLine.batch_id == int(batch_id),
                PayoutLine.artist_id == int(artist_id),
                PayoutLine.song_id == sid,
            )
            .distinct()
            .all()
        )
        line_types = sorted({str(r[0] or "") for r in lt_rows if r[0]})

        split_row = (
            db.query(SongArtistSplit.split_bps)
            .filter(
                SongArtistSplit.song_id == sid,
                SongArtistSplit.artist_id == int(artist_id),
            )
            .one_or_none()
        )
        artist_split_bps = int(split_row[0]) if split_row is not None else 0

        songs_out.append(
            {
                "artist_split_bps": artist_split_bps,
                "cents": c,
                "contributing_users": len(contributor_ids),
                "line_types": line_types,
                "raw_units": int(r_sum),
                "song_id": sid,
                "streams_count": None,
                "weighted_units": int(w_sum),
            }
        )

    line_total_check = (
        db.query(func.coalesce(func.sum(PayoutLine.amount_cents), 0))
        .filter(
            PayoutLine.batch_id == int(batch_id),
            PayoutLine.artist_id == int(artist_id),
        )
        .scalar()
        or 0
    )
    if int(line_total_check) != int(total_cents):
        raise RuntimeError(
            f"Breakdown total mismatch batch={batch_id} artist={artist_id}: "
            f"computed={total_cents} lines={line_total_check}"
        )

    policy_share_milli = int(round(float(snap.policy_artist_share or 0.0) * 1000))

    splits_digest = compute_splits_digest(songs_out)

    breakdown: Dict[str, Any] = {
        "algorithm": {
            "antifraud_version": str(batch.antifraud_version or ""),
            "batch_calculation_version": str(batch.calculation_version or ""),
            "policy_artist_share_milli": policy_share_milli,
            "policy_id": str(snap.policy_id or ""),
            "snapshot_calculation_version": str(snap.calculation_version or ""),
        },
        "artist_id": int(artist_id),
        "batch_id": int(batch_id),
        "currency": str(batch.currency or "USD"),
        "schema_version": "payout_breakdown.v1",
        "snapshot_id": int(snapshot_id),
        "songs": songs_out,
        "splits_digest": splits_digest,
        "total_cents": int(total_cents),
    }
    return breakdown


def breakdown_totals_match(breakdown: Dict[str, Any]) -> bool:
    songs = breakdown.get("songs") or []
    if not isinstance(songs, list):
        return False
    s = sum(int(x.get("cents") or 0) for x in songs if isinstance(x, dict))
    return int(breakdown.get("total_cents") or 0) == s
