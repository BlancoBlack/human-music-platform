from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal
from app.models.artist import Artist
from app.models.payout_batch import PayoutBatch
from app.models.payout_line import PayoutLine
from app.models.payout_input_snapshot import PayoutInputSnapshot
from app.models.song_artist_split import SongArtistSplit
from app.models.snapshot_listening_input import SnapshotListeningInput
from app.models.snapshot_user_pool import SnapshotUserPool
from app.models.song import Song
from app.services.royalty_split import split_song_cents


TREASURY_ARTIST_SYSTEM_KEY = "TREASURY"
TREASURY_SONG_SYSTEM_KEY = "TREASURY_SINK"


def _default_splits_for_single_artist(artist_id: int) -> List[Tuple[int, int]]:
    """
    MVP placeholder splits:
    - single artist owns 100% in basis points
    Later, this function should be replaced with real per-song split lookup,
    but expected_count logic must continue to use the same source of truth.
    """
    return [(int(artist_id), 10000)]


def _validate_and_sort_splits_or_raise(
    *, song_id: int, splits: List[Tuple[int, int]]
) -> List[Tuple[int, int]]:
    """
    Strict split validation:
    - no duplicate artist_ids
    - each split_bps in [0, 10000]
    - sum(split_bps) == 10000
    - deterministic ordering by artist_id ASC
    Failure policy: raise RuntimeError (caller should fail batch).
    """
    if not splits:
        raise RuntimeError(f"Invalid splits for song_id={song_id}: empty split set")

    seen = set()
    total = 0
    out: List[Tuple[int, int]] = []
    for artist_id, split_bps in splits:
        aid = int(artist_id)
        if aid in seen:
            raise RuntimeError(
                f"Invalid splits for song_id={song_id}: duplicate artist_id={aid}"
            )
        seen.add(aid)

        bps = int(split_bps)
        if bps < 0 or bps > 10000:
            raise RuntimeError(
                f"Invalid splits for song_id={song_id}, artist_id={aid}: split_bps={bps}"
            )
        total += bps
        out.append((aid, bps))

    if total != 10000:
        raise RuntimeError(
            f"Invalid splits for song_id={song_id}: sum(split_bps)={total}, expected 10000"
        )

    out.sort(key=lambda x: x[0])
    return out


@dataclass(frozen=True)
class _SongAllocation:
    song_id: int
    amount_cents: int
    artist_id: int
    line_type: str  # 'royalty' | 'treasury'
    idempotency_key: str


def _compute_largest_remainder_allocation(
    *, units_by_song_id: Dict[int, int], total_units: int, pool_cents: int
) -> Dict[int, int]:
    """
    Integer-only Largest Remainder allocation:
    - exact = units_i * pool_cents / total_units
    - base = floor(exact)
    - remainder is (units_i * pool_cents) % total_units
    - distribute leftover cents by highest remainder DESC, song_id ASC
    """
    if total_units <= 0:
        raise RuntimeError("total_units must be > 0 for allocation")
    if pool_cents < 0:
        raise RuntimeError("pool_cents must be >= 0")

    allocations: Dict[int, int] = {}
    sum_base = 0
    ranked: List[Tuple[int, int]] = []  # (remainder, song_id)

    for song_id, units_i in units_by_song_id.items():
        if units_i < 0:
            raise RuntimeError("units_i must be >= 0")

        numerator = units_i * pool_cents
        base = numerator // total_units
        remainder = numerator % total_units

        allocations[song_id] = int(base)
        sum_base += int(base)
        ranked.append((int(remainder), int(song_id)))

    leftover = pool_cents - sum_base
    if leftover < 0:
        raise RuntimeError("Conservation error: negative leftover")
    if leftover == 0:
        return allocations

    # For Largest Remainder, leftover is always < number of items; be strict.
    if leftover > len(ranked):
        raise RuntimeError("Conservation error: leftover exceeds song count")

    # Sort remainder DESC, then song_id ASC.
    ranked.sort(key=lambda x: (-x[0], x[1]))

    for i in range(leftover):
        song_id = ranked[i][1]
        allocations[song_id] += 1

    if sum(allocations.values()) != pool_cents:
        raise RuntimeError("Conservation error: allocation sum mismatch")

    return allocations


def generate_payout_lines(
    batch_id: int,
    *,
    auto_run_settlement: Optional[bool] = None,
    auto_settlement_async: Optional[bool] = None,
) -> int:
    """
    MVP payout generation from snapshot tables.

    - Uses sealed snapshot for this batch.
    - No floats in allocation math.
    - Single-artist-per-song (no splits yet).
    - Deterministic cent conservation per user.
    - After successful commit (status ``finalized``), optionally runs on-chain
      settlement (see ``auto_run_settlement`` / ``AUTO_SETTLEMENT_AFTER_FINALIZE``).
    - ``auto_settlement_async`` (or env ``AUTO_SETTLEMENT_ASYNC``, default async):
      if True, settlement runs in a daemon thread; if False, blocks until the worker
      returns (recommended for short-lived scripts).
    """
    db = SessionLocal()

    try:
        batch = db.query(PayoutBatch).filter(PayoutBatch.id == batch_id).first()
        if batch is None:
            raise RuntimeError(f"payout_batches not found for batch_id={batch_id}")
        if batch.status == "finalized":
            raise RuntimeError(f"Batch {batch_id} is already finalized")
        if batch.status == "posted":
            raise RuntimeError(f"Batch {batch_id} is already posted")
        if batch.status != "calculating":
            raise RuntimeError(
                f"generate_payout_lines requires batch status='calculating', got '{batch.status}'"
            )

        # Snapshot selection is explicit via payout_batches.snapshot_id (no heuristics).
        if batch.snapshot_id is None:
            raise RuntimeError(f"Batch {batch_id} has no snapshot_id")
        snapshot = (
            db.query(PayoutInputSnapshot)
            .filter(PayoutInputSnapshot.id == int(batch.snapshot_id))
            .one_or_none()
        )
        if snapshot is None:
            raise RuntimeError(f"Snapshot not found for batch.snapshot_id={batch.snapshot_id}")
        if snapshot.snapshot_state != "sealed":
            raise RuntimeError(f"Snapshot {snapshot.id} is not sealed")
        snapshot_id = int(snapshot.id)

        # Resolve treasury entities (DB-level invariant required).
        treasury_artist = (
            db.query(Artist)
            .filter(Artist.system_key == TREASURY_ARTIST_SYSTEM_KEY)
            .one_or_none()
        )
        treasury_song = (
            db.query(Song)
            .filter(Song.system_key == TREASURY_SONG_SYSTEM_KEY)
            .one_or_none()
        )
        if treasury_artist is None or treasury_song is None:
            raise RuntimeError("Treasury invariant failed: missing treasury artist/song")

        currency = batch.currency

        # Collect all unique song_ids referenced by this snapshot (single query).
        snapshot_song_ids = [
            int(song_id)
            for (song_id,) in db.query(SnapshotListeningInput.song_id)
            .filter(SnapshotListeningInput.snapshot_id == snapshot_id)
            .distinct()
            .order_by(SnapshotListeningInput.song_id.asc())
            .all()
        ]

        # Preload song -> artist for fallback resolution (single query).
        # Note: this is used only when no split rows exist for a song.
        song_to_artist: Dict[int, int] = {}
        if snapshot_song_ids:
            songs = (
                db.query(Song.id, Song.artist_id)
                .filter(Song.id.in_(snapshot_song_ids))
                .all()
            )
            song_to_artist = {int(s.id): int(s.artist_id) for s in songs if s.artist_id is not None}

        # Load ALL splits for these song_ids in ONE query (no N+1).
        splits_map: Dict[int, List[Tuple[int, int]]] = {sid: [] for sid in snapshot_song_ids}
        if snapshot_song_ids:
            split_rows = (
                db.query(SongArtistSplit.song_id, SongArtistSplit.artist_id, SongArtistSplit.split_bps)
                .filter(SongArtistSplit.song_id.in_(snapshot_song_ids))
                .order_by(SongArtistSplit.song_id.asc(), SongArtistSplit.artist_id.asc())
                .all()
            )
            for song_id, artist_id, split_bps in split_rows:
                sid = int(song_id)
                splits_map.setdefault(sid, []).append((int(artist_id), int(split_bps)))

        def get_splits_for_song(song_id: int) -> List[Tuple[int, int]]:
            """
            Resolve splits for a song WITHOUT any DB queries.
            - If split rows exist: strict-validate and return sorted list.
            - Else: fallback to (song.artist_id, 10000); if missing -> raise.
            """
            sid = int(song_id)
            raw_splits = splits_map.get(sid) or []
            if raw_splits:
                # Always apply deterministic ordering (artist_id ASC) + strict validation.
                return _validate_and_sort_splits_or_raise(song_id=sid, splits=list(raw_splits))

            fallback_artist_id = song_to_artist.get(sid)
            if fallback_artist_id is None:
                raise RuntimeError(
                    f"Song {sid} has no split rows and song.artist_id is NULL/unknown"
                )
            return _default_splits_for_single_artist(fallback_artist_id)

        # Deterministic processing order.
        snapshot_users = (
            db.query(SnapshotUserPool)
            .filter(SnapshotUserPool.snapshot_id == snapshot_id)
            .order_by(SnapshotUserPool.user_id.asc())
            .all()
        )

        inserted_count = 0

        for up in snapshot_users:
            user_id = int(up.user_id)
            pool_cents = int(up.user_pool_cents)

            listening_rows = (
                db.query(
                    SnapshotListeningInput.song_id,
                    SnapshotListeningInput.raw_units_i,
                    SnapshotListeningInput.qualified_units_i,
                )
                .filter(SnapshotListeningInput.snapshot_id == snapshot_id)
                .filter(SnapshotListeningInput.user_id == user_id)
                .order_by(SnapshotListeningInput.song_id.asc())
                .all()
            )

            qualified_total = sum(int(r.qualified_units_i or 0) for r in listening_rows)
            raw_total = sum(int(r.raw_units_i or 0) for r in listening_rows)

            # Expected number of payout_lines for this user.
            # With multi-artist support, this is:
            #   sum over songs: number of artists returned by split system for that song.
            if qualified_total > 0 or raw_total > 0:
                song_ids = sorted(set(int(r.song_id) for r in listening_rows))
                expected_count = 0
                for song_id in song_ids:
                    expected_count += len(get_splits_for_song(song_id))
            else:
                # Treasury mode: split system uses treasury artist at 100%.
                expected_count = len(
                    _default_splits_for_single_artist(int(treasury_artist.id))
                )

            existing_user_lines_count = (
                db.query(PayoutLine.id)
                .filter(PayoutLine.batch_id == batch_id)
                .filter(PayoutLine.user_id == user_id)
                .count()
            )
            if existing_user_lines_count > 0:
                # Fix 1: user-level idempotency.
                # Do not process partial users. If row count differs, fail loudly.
                if int(existing_user_lines_count) != int(expected_count):
                    raise RuntimeError(
                        f"Partial user detected for user_id={user_id}: "
                        f"existing_lines={existing_user_lines_count}, expected_lines={expected_count}"
                    )
                # Conservation check (still required).
                actual_sum = (
                    db.query(func.sum(PayoutLine.amount_cents))
                    .filter(PayoutLine.batch_id == batch_id)
                    .filter(PayoutLine.user_id == user_id)
                    .scalar()
                )
                if int(actual_sum or 0) != pool_cents:
                    raise RuntimeError(
                        f"Conservation failed for user_id={user_id}: "
                        f"actual={int(actual_sum or 0)} expected={pool_cents}"
                    )
                continue

            if qualified_total > 0:
                mode = "qualified"
                total_units = qualified_total
                units_by_song_id = {
                    int(r.song_id): int(r.qualified_units_i or 0) for r in listening_rows
                }
            elif raw_total > 0:
                mode = "raw_fallback"
                total_units = raw_total
                units_by_song_id = {
                    int(r.song_id): int(r.raw_units_i or 0) for r in listening_rows
                }
            else:
                # Treasury fallback: user has zero denominators.
                amount_cents = pool_cents
                treasury_song_id = int(treasury_song.id)
                treasury_artist_id = int(treasury_artist.id)

                # Phase 3.2B: treasury also goes through split system.
                splits = _default_splits_for_single_artist(treasury_artist_id)
                artist_allocations = split_song_cents(
                    song_cents=amount_cents, splits=splits
                )

                for artist_id, artist_cents in artist_allocations:
                    key = (
                        f"v2:{batch_id}:u:{user_id}:s:{treasury_song_id}:a:{artist_id}"
                    )
                    db.add(
                        PayoutLine(
                            batch_id=batch_id,
                            user_id=user_id,
                            song_id=treasury_song_id,
                            artist_id=int(artist_id),
                            amount_cents=int(artist_cents),
                            currency=currency,
                            line_type="treasury",
                            idempotency_key=key,
                        )
                    )
                db.flush()
                inserted_count += len(artist_allocations)

                # Fix 2: expected row count validation.
                inserted_for_user = (
                    db.query(PayoutLine.id)
                    .filter(PayoutLine.batch_id == batch_id)
                    .filter(PayoutLine.user_id == user_id)
                    .count()
                )
                if int(inserted_for_user) != int(expected_count):
                    raise RuntimeError(
                        f"Missing payout lines for user_id={user_id}: inserted={inserted_for_user}, expected={expected_count}"
                    )

                # Conservation check (Step 7).
                actual_sum = (
                    db.query(func.sum(PayoutLine.amount_cents))
                    .filter(PayoutLine.batch_id == batch_id)
                    .filter(PayoutLine.user_id == user_id)
                    .scalar()
                )
                if int(actual_sum or 0) != pool_cents:
                    raise RuntimeError(
                        f"Conservation failed for user_id={user_id}: actual={int(actual_sum or 0)} expected={pool_cents}"
                    )
                continue

            if total_units <= 0:
                raise RuntimeError("Invalid total_units computed for allocation")

            allocations_by_song_id = _compute_largest_remainder_allocation(
                units_by_song_id=units_by_song_id,
                total_units=total_units,
                pool_cents=pool_cents,
            )

            song_ids = sorted(allocations_by_song_id.keys())
            intended: List[_SongAllocation] = []
            for song_id in song_ids:
                amount_cents = int(allocations_by_song_id.get(song_id, 0))
                splits = get_splits_for_song(song_id)
                artist_allocations = split_song_cents(
                    song_cents=amount_cents, splits=splits
                )
                # Deterministic output: split_song_cents sorts by artist_id.
                for artist_id, artist_cents in artist_allocations:
                    key = f"v2:{batch_id}:u:{user_id}:s:{song_id}:a:{artist_id}"
                    intended.append(
                        _SongAllocation(
                            song_id=song_id,
                            amount_cents=int(artist_cents),
                            artist_id=int(artist_id),
                            line_type="royalty",
                            idempotency_key=key,
                        )
                    )

            for t in intended:
                db.add(
                    PayoutLine(
                        batch_id=batch_id,
                        user_id=user_id,
                        song_id=t.song_id,
                        artist_id=t.artist_id,
                        amount_cents=t.amount_cents,
                        currency=currency,
                        line_type=t.line_type,
                        idempotency_key=t.idempotency_key,
                    )
                )
            db.flush()
            inserted_count += len(intended)

            # Fix 2: expected row count validation.
            inserted_for_user = (
                db.query(PayoutLine.id)
                .filter(PayoutLine.batch_id == batch_id)
                .filter(PayoutLine.user_id == user_id)
                .count()
            )
            if int(inserted_for_user) != int(expected_count):
                raise RuntimeError(
                    f"Missing payout lines for user_id={user_id}: inserted={inserted_for_user}, expected={expected_count}"
                )

            # Step 7: per-user conservation check against DB.
            actual_sum = (
                db.query(func.sum(PayoutLine.amount_cents))
                .filter(PayoutLine.batch_id == batch_id)
                .filter(PayoutLine.user_id == user_id)
                .scalar()
            )
            if int(actual_sum or 0) != pool_cents:
                raise RuntimeError(
                    f"Conservation failed for user_id={user_id}: actual={int(actual_sum or 0)} expected={pool_cents}"
                )

        # Lifecycle transition: calculating -> finalized
        batch.status = "finalized"
        batch.finalized_at = func.now()
        db.add(batch)
        db.commit()

        if auto_run_settlement is None:
            auto_run_settlement = os.getenv(
                "AUTO_SETTLEMENT_AFTER_FINALIZE", "1"
            ).lower() not in ("0", "false", "no", "off")
        if auto_settlement_async is None:
            auto_settlement_async = os.getenv(
                "AUTO_SETTLEMENT_ASYNC", "1"
            ).lower() not in ("0", "false", "no", "off")
        if auto_run_settlement:
            from app.workers.settlement_worker import schedule_auto_settlement_after_finalize

            schedule_auto_settlement_after_finalize(
                int(batch_id),
                asynchronous=bool(auto_settlement_async),
            )

        return inserted_count

    except IntegrityError as e:
        db.rollback()
        raise RuntimeError(f"Snapshot->lines generation failed due to integrity error: {e}") from e
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def post_batch(batch_id: int) -> None:
    """
    Lifecycle placeholder transition:
    finalized -> posted
    """
    db = SessionLocal()
    try:
        batch = db.query(PayoutBatch).filter(PayoutBatch.id == batch_id).first()
        if batch is None:
            raise RuntimeError(f"payout_batches not found for batch_id={batch_id}")
        if batch.status != "finalized":
            raise RuntimeError(
                f"post_batch requires batch status='finalized', got '{batch.status}'"
            )
        batch.status = "posted"
        db.add(batch)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

