"""
Read-only Global Model Comparison on a sealed payout input snapshot.

Mirrors V1 ``compare_models`` UX using ``snapshot_user_pools`` and
``snapshot_listening_inputs`` only for monetary/listening inputs (batch header,
snapshot header, and ``Song`` rows are used for routing and system-song rules).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.payout_batch import PayoutBatch
from app.models.payout_input_snapshot import PayoutInputSnapshot
from app.models.snapshot_listening_input import SnapshotListeningInput
from app.models.snapshot_user_pool import SnapshotUserPool
from app.models.song import Song
from app.services.payout_service import TREASURY_SONG_SYSTEM_KEY


def _largest_remainder_song_cents(
    *, units_by_song: Dict[int, int], pool_cents: int
) -> Dict[int, int]:
    """Integer Hamilton / largest remainder: base = (u * P) // T, rem = (u * P) % T."""
    if pool_cents < 0:
        raise ValueError("pool_cents must be >= 0")
    if pool_cents == 0:
        return {int(sid): 0 for sid in units_by_song}

    total_units = sum(int(units_by_song[s]) for s in units_by_song)
    if total_units <= 0:
        return {}

    allocations: Dict[int, int] = {}
    sum_base = 0
    ranked: List[Tuple[int, int]] = []

    for song_id in sorted(units_by_song.keys()):
        units_i = int(units_by_song[song_id])
        if units_i < 0:
            raise ValueError("units_i must be >= 0")
        numerator = units_i * int(pool_cents)
        base = numerator // total_units
        remainder = numerator % total_units
        allocations[int(song_id)] = int(base)
        sum_base += int(base)
        ranked.append((int(remainder), int(song_id)))

    leftover = int(pool_cents) - sum_base
    if leftover < 0:
        raise RuntimeError("Global model V2: negative leftover in allocation")
    if leftover > len(ranked):
        raise RuntimeError("Global model V2: leftover exceeds song count")

    ranked.sort(key=lambda x: (-x[0], x[1]))
    for i in range(leftover):
        sid = ranked[i][1]
        allocations[sid] = int(allocations[sid]) + 1

    if sum(allocations.values()) != int(pool_cents):
        raise RuntimeError("Global model V2: allocation sum mismatch")

    return allocations


def compare_models_v2_snapshot(db: Session, batch_id: int, user_id: int) -> Dict[str, Any]:
    """
    Deterministic snapshot-only comparison:
    - user model: exact, ledger-equivalent recomputation from snapshot inputs
    - global model: benchmark from raw snapshot units across all users (non-system songs)

    Requires ``payout_batches.snapshot_id`` set to a **sealed** snapshot.
    """
    batch = db.query(PayoutBatch).filter(PayoutBatch.id == int(batch_id)).one_or_none()
    if batch is None:
        raise RuntimeError(f"payout_batches not found for batch_id={batch_id}")
    if batch.snapshot_id is None:
        raise RuntimeError(f"Batch {batch_id} has no snapshot_id")

    snapshot = (
        db.query(PayoutInputSnapshot)
        .filter(PayoutInputSnapshot.id == int(batch.snapshot_id))
        .one_or_none()
    )
    if snapshot is None:
        raise RuntimeError(f"Snapshot not found id={batch.snapshot_id}")
    if snapshot.snapshot_state != "sealed":
        raise RuntimeError(
            f"compare_models_v2_snapshot requires sealed snapshot, got {snapshot.snapshot_state!r}"
        )

    snapshot_id = int(snapshot.id)

    snap_user = (
        db.query(SnapshotUserPool)
        .filter(
            SnapshotUserPool.snapshot_id == snapshot_id,
            SnapshotUserPool.user_id == int(user_id),
        )
        .one_or_none()
    )
    if snap_user is None:
        return {
            "user_id": int(user_id),
            "batch_id": int(batch_id),
            "snapshot_id": snapshot_id,
            "mode": "treasury",
            "total_user_pool_cents": 0,
            "user_cents_by_song": {},
            "global_cents_by_song": {},
            "comparison": [],
        }

    # Snapshot is the single economic source of truth:
    # user_pool_cents is already artist-share reduced at snapshot build time.
    pool_cents = int(snap_user.user_pool_cents or 0)

    listen_rows = (
        db.query(
            SnapshotListeningInput.song_id,
            SnapshotListeningInput.raw_units_i,
            SnapshotListeningInput.qualified_units_i,
        )
        .filter(
            SnapshotListeningInput.snapshot_id == snapshot_id,
            SnapshotListeningInput.user_id == int(user_id),
        )
        .all()
    )

    q_by: Dict[int, int] = defaultdict(int)
    r_by: Dict[int, int] = defaultdict(int)
    for song_id, raw_i, qual_i in listen_rows:
        sid = int(song_id)
        q_by[sid] += int(qual_i or 0)
        r_by[sid] += int(raw_i or 0)

    qualified_total = sum(q_by.values())
    raw_total = sum(r_by.values())

    mode: str
    units_by_song: Dict[int, int]
    user_alloc: Dict[int, int] = {}

    if qualified_total > 0:
        mode = "qualified"
        units_by_song = {s: int(v) for s, v in q_by.items() if v > 0}
        user_alloc = _largest_remainder_song_cents(
            units_by_song=units_by_song, pool_cents=pool_cents
        )
    elif raw_total > 0:
        mode = "raw"
        units_by_song = {s: int(v) for s, v in r_by.items() if v > 0}
        user_alloc = _largest_remainder_song_cents(
            units_by_song=units_by_song, pool_cents=pool_cents
        )
    else:
        mode = "treasury"
        units_by_song = {}
        treasury_row = (
            db.query(Song.id)
            .filter(Song.system_key == TREASURY_SONG_SYSTEM_KEY)
            .one_or_none()
        )
        if treasury_row is not None and pool_cents > 0:
            user_alloc = {int(treasury_row.id): int(pool_cents)}
        else:
            user_alloc = {}

    # Global benchmark uses raw validated units and excludes system songs.
    global_rows = (
        db.query(
            SnapshotListeningInput.song_id,
            func.sum(SnapshotListeningInput.raw_units_i),
        )
        .filter(SnapshotListeningInput.snapshot_id == snapshot_id)
        .group_by(SnapshotListeningInput.song_id)
        .all()
    )
    global_raw_by_song_all: Dict[int, int] = {
        int(sid): int(s or 0) for sid, s in global_rows
    }

    song_ids_needed = set(user_alloc.keys()) | set(global_raw_by_song_all.keys())
    system_song_ids: set[int] = set()
    if song_ids_needed:
        for sid, is_sys in (
            db.query(Song.id, Song.is_system)
            .filter(Song.id.in_(sorted(song_ids_needed)))
            .all()
        ):
            if bool(is_sys):
                system_song_ids.add(int(sid))

    non_system_global_units = {
        s: u
        for s, u in global_raw_by_song_all.items()
        if s not in system_song_ids and int(u) > 0
    }
    global_alloc = _largest_remainder_song_cents(
        units_by_song=non_system_global_units,
        pool_cents=pool_cents,
    ) if non_system_global_units and pool_cents > 0 else {}

    all_song_ids = sorted(set(user_alloc.keys()) | set(global_alloc.keys()))

    comparison: List[Dict[str, Any]] = []

    for sid in all_song_ids:
        user_cents = int(user_alloc.get(sid, 0))
        global_cents = int(global_alloc.get(sid, 0))
        difference_cents = int(user_cents - global_cents)

        comparison.append(
            {
                "song_id": int(sid),
                "user_cents": user_cents,
                "global_cents": global_cents,
                "difference_cents": difference_cents,
            }
        )

    user_total = sum(int(v) for v in user_alloc.values())
    global_total = sum(int(v) for v in global_alloc.values())
    if user_total != int(pool_cents):
        raise RuntimeError(
            f"user comparison conservation failed: got={user_total}, expected={pool_cents}"
        )
    if global_total != int(pool_cents):
        raise RuntimeError(
            f"global comparison conservation failed: got={global_total}, expected={pool_cents}"
        )

    return {
        "user_id": int(user_id),
        "batch_id": int(batch_id),
        "snapshot_id": snapshot_id,
        "total_user_pool_cents": int(pool_cents),
        "mode": mode,
        "user_cents_by_song": {int(k): int(v) for k, v in sorted(user_alloc.items())},
        "global_cents_by_song": {int(k): int(v) for k, v in sorted(global_alloc.items())},
        "comparison": comparison,
    }


def compare_models_v2(db: Session, batch_id: int, user_id: int) -> Dict[str, Any]:
    """
    Backward-compatible entrypoint; now powered by snapshot-only integer model.
    """
    result = compare_models_v2_snapshot(db=db, batch_id=batch_id, user_id=user_id)

    # Legacy compatibility aliases for callers expecting older key names.
    result["pool_cents_artist_share"] = int(result["total_user_pool_cents"])
    if result.get("mode") == "treasury":
        result["mode"] = "treasury_fallback"

    legacy_mode = str(result.get("mode") or "")
    user_song_ids = set(int(sid) for sid in result.get("user_cents_by_song", {}).keys())

    filtered_rows: List[Dict[str, Any]] = []
    for row in result.get("comparison", []):
        # Keep legacy behavior focused on global benchmark songs.
        if int(row.get("global_cents", 0)) <= 0:
            continue

        global_payout = round(float(int(row["global_cents"])) / 100.0, 2)
        if legacy_mode == "treasury_fallback":
            user_payout = None
            user_share = None
            difference = None
        elif int(row["song_id"]) in user_song_ids:
            user_payout = round(float(int(row["user_cents"])) / 100.0, 2)
            user_share = None
            difference = round(user_payout - global_payout, 2)
        else:
            user_payout = None
            user_share = None
            difference = None

        row["user_payout"] = user_payout
        row["pool_amount"] = global_payout
        row["difference"] = difference
        row["user_share"] = user_share
        row["pool_share"] = None
        row["user_model"] = {"share": user_share, "payout": user_payout}
        row["global_model"] = {"share": None, "payout": global_payout}
        filtered_rows.append(row)

    result["comparison"] = filtered_rows

    return result
