"""
Listening pipeline integrity utilities.

These helpers are intentionally internal and are not wired to API routes.
"""

from __future__ import annotations

from sqlalchemy import func

from app.core.database import SessionLocal
from app.models.global_listening_aggregate import GlobalListeningAggregate
from app.models.listening_aggregate import ListeningAggregate
from app.models.listening_event import ListeningEvent


def rebuild_listening_aggregates() -> dict:
    """
    Rebuild ListeningAggregate from ListeningEvent source-of-truth
    using the exact same formulas as listen_worker.py.
    """
    db = SessionLocal()
    try:
        epsilon = 1e-9
        events = (
            db.query(ListeningEvent)
            .filter(ListeningEvent.user_id.isnot(None), ListeningEvent.song_id.isnot(None))
            .all()
        )

        rebuilt_map: dict[tuple[int, int], dict[str, float]] = {}
        for e in events:
            key = (int(e.user_id), int(e.song_id))
            if key not in rebuilt_map:
                rebuilt_map[key] = {"total_duration": 0.0, "weighted_duration": 0.0}

            if e.is_valid:
                vd = float(e.validated_duration or 0)
                w = float(e.weight or 0)
                rebuilt_map[key]["total_duration"] += vd
                rebuilt_map[key]["weighted_duration"] += vd * w
            else:
                rebuilt_map[key]["total_duration"] += 0.0
                rebuilt_map[key]["weighted_duration"] += 0.0

        db.query(ListeningAggregate).delete(synchronize_session=False)

        created = 0
        for (user_id, song_id), values in rebuilt_map.items():
            aggregate = ListeningAggregate(
                user_id=user_id,
                song_id=song_id,
                total_duration=float(values["total_duration"]),
                weighted_duration=float(values["weighted_duration"]),
            )
            db.add(aggregate)
            created += 1

        db.commit()

        db_rows = (
            db.query(ListeningAggregate)
            .filter(ListeningAggregate.user_id.isnot(None), ListeningAggregate.song_id.isnot(None))
            .all()
        )
        db_map: dict[tuple[int, int], dict[str, float]] = {
            (int(a.user_id), int(a.song_id)): {
                "total_duration": float(a.total_duration or 0.0),
                "weighted_duration": float(a.weighted_duration or 0.0),
            }
            for a in db_rows
        }
        all_keys = set(rebuilt_map.keys()) | set(db_map.keys())
        for key in all_keys:
            expected = rebuilt_map.get(key, {"total_duration": 0.0, "weighted_duration": 0.0})
            actual = db_map.get(key, {"total_duration": 0.0, "weighted_duration": 0.0})
            if abs(expected["total_duration"] - actual["total_duration"]) > epsilon:
                raise ValueError(f"ListeningAggregate total_duration mismatch for {key}")
            if abs(expected["weighted_duration"] - actual["weighted_duration"]) > epsilon:
                raise ValueError(f"ListeningAggregate weighted_duration mismatch for {key}")

        return {
            "rebuilt": True,
            "aggregate_rows": created,
        }
    finally:
        db.close()


def rebuild_global_listening_aggregates() -> dict:
    """
    Rebuild GlobalListeningAggregate from ListeningEvent source-of-truth
    using the exact same formulas as listen_worker.py.
    """
    db = SessionLocal()
    try:
        epsilon = 1e-9
        events = db.query(ListeningEvent).filter(ListeningEvent.song_id.isnot(None)).all()

        rebuilt_map: dict[int, float] = {}
        for e in events:
            song_id = int(e.song_id)
            if song_id not in rebuilt_map:
                rebuilt_map[song_id] = 0.0

            if e.is_valid:
                rebuilt_map[song_id] += float(e.validated_duration or 0)
            else:
                rebuilt_map[song_id] += 0.0

        db.query(GlobalListeningAggregate).delete(synchronize_session=False)

        created = 0
        for song_id, total_duration in rebuilt_map.items():
            db.add(
                GlobalListeningAggregate(
                    song_id=song_id,
                    total_duration=float(total_duration),
                )
            )
            created += 1

        db.commit()

        db_rows = db.query(GlobalListeningAggregate).filter(GlobalListeningAggregate.song_id.isnot(None)).all()
        db_map: dict[int, float] = {
            int(a.song_id): float(a.total_duration or 0.0)
            for a in db_rows
        }
        all_keys = set(rebuilt_map.keys()) | set(db_map.keys())
        for key in all_keys:
            expected = rebuilt_map.get(key, 0.0)
            actual = db_map.get(key, 0.0)
            if abs(expected - actual) > epsilon:
                raise ValueError(f"GlobalListeningAggregate total_duration mismatch for song_id={key}")

        return {
            "rebuilt": True,
            "global_aggregate_rows": created,
        }
    finally:
        db.close()


def check_aggregate_consistency() -> list[dict]:
    """
    Compare aggregate totals vs event-derived totals for each (user_id, song_id).

    Returns one row per mismatch:
    - user_id
    - song_id
    - events_total_duration
    - aggregate_total_duration
    - diff
    """
    db = SessionLocal()
    try:
        event_rows = (
            db.query(
                ListeningEvent.user_id,
                ListeningEvent.song_id,
                func.sum(ListeningEvent.duration),
            )
            .filter(ListeningEvent.user_id.isnot(None), ListeningEvent.song_id.isnot(None))
            .group_by(ListeningEvent.user_id, ListeningEvent.song_id)
            .all()
        )
        event_map: dict[tuple[int, int], int] = {
            (int(user_id), int(song_id)): int(float(summed_duration or 0))
            for user_id, song_id, summed_duration in event_rows
        }

        aggregate_rows = db.query(ListeningAggregate).all()
        aggregate_map: dict[tuple[int, int], int] = {
            (int(a.user_id), int(a.song_id)): int(a.total_duration or 0)
            for a in aggregate_rows
            if a.user_id is not None and a.song_id is not None
        }

        mismatches: list[dict] = []
        for key in sorted(set(event_map.keys()) | set(aggregate_map.keys())):
            events_total = event_map.get(key, 0)
            aggregate_total = aggregate_map.get(key, 0)
            if events_total != aggregate_total:
                user_id, song_id = key
                mismatches.append(
                    {
                        "user_id": user_id,
                        "song_id": song_id,
                        "events_total_duration": events_total,
                        "aggregate_total_duration": aggregate_total,
                        "diff": events_total - aggregate_total,
                    }
                )

        return mismatches
    finally:
        db.close()
