import argparse
import inspect
import random
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
import sys

from sqlalchemy import func

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import SessionLocal
from app.models.listening_event import ListeningEvent
from app.models.payout_batch import PayoutBatch
from app.models.song import Song
from app.models.user import User
from app.models.user_balance import UserBalance
from app.services.user_service import (
    SEED_LISTENER_PLACEHOLDER_PASSWORD,
    create_user,
)
from app.services.global_model_v2_service import compare_models_v2_snapshot
from app.services.payout_service import calculate_user_distribution, ensure_treasury_entities
from app.services.payout_v2_snapshot_engine import generate_payout_lines
from app.services.snapshot_service import build_snapshot
from app.services.stream_service import StreamService
from app.workers.listen_worker import process_listening_event
from app.seeding.seed_common import (
    DEFAULT_TOTAL_EVENTS,
    _pick_days_ago,
    _print_summary,
    _random_duration,
    _set_user_balances,
    _timestamp_for_days_ago,
    _upsert_artists,
    _upsert_songs,
    _upsert_users,
    ensure_schema,
    reset_existing_data,
)


def _normalize_v1_mode(v1_rows: list[dict]) -> str:
    if v1_rows:
        raw_mode = v1_rows[0].get("mode")
    else:
        raw_mode = "treasury_fallback"
    if raw_mode == "weighted":
        return "qualified"
    if raw_mode == "raw_fallback":
        return "raw"
    return "treasury"


def _collect_validity_stats() -> dict[str, float]:
    db = SessionLocal()
    try:
        total_events = int(db.query(func.count(ListeningEvent.id)).scalar() or 0)
        valid_events = int(
            db.query(func.count(ListeningEvent.id))
            .filter(ListeningEvent.is_valid.is_(True))
            .scalar()
            or 0
        )
        invalid_events = total_events - valid_events
        valid_pct = (
            (float(valid_events) / float(total_events) * 100.0) if total_events > 0 else 0.0
        )
        avg_weight = float(db.query(func.avg(ListeningEvent.weight)).scalar() or 0.0)
        return {
            "total_events": total_events,
            "valid_events": valid_events,
            "invalid_events": invalid_events,
            "valid_pct": valid_pct,
            "avg_weight": avg_weight,
        }
    finally:
        db.close()


def _simulate_events(users: list[User], songs: list, total_events: int) -> dict[str, object]:
    """
    Realistic simulation using StreamService + explicit worker processing.
    Timestamps are set at insert via ``event_timestamp`` (no post-hoc mutation).
    """
    service = StreamService()
    supports_event_timestamp = "event_timestamp" in inspect.signature(
        service.process_stream
    ).parameters

    u1_weights = [0.30, 0.26, 0.20, 0.14, 0.06, 0.04]
    u2_weights = [0.05, 0.08, 0.25, 0.24, 0.19, 0.19]
    song_ids = [s.id for s in songs]
    full_track_lengths = {s.id: random.randint(190, 320) for s in songs}

    user_event_targets = {
        users[0].id: int(total_events * 0.55),
        users[1].id: total_events - int(total_events * 0.55),
    }
    last_planned_ts_by_user_song: dict[tuple[int, int], object] = {}

    days_counter: dict[int, int] = defaultdict(int)
    inserted = 0
    failed = 0
    worker_failures = 0
    error_samples: list[str] = []

    db = SessionLocal()
    try:
        for user in users:
            weights = u1_weights if user.id == users[0].id else u2_weights
            for _ in range(user_event_targets[user.id]):
                days_ago = _pick_days_ago()
                song_id = random.choices(song_ids, weights=weights, k=1)[0]
                ts = _timestamp_for_days_ago(days_ago)
                spacing_key = (int(user.id), int(song_id))

                last_ts = last_planned_ts_by_user_song.get(spacing_key)
                if last_ts is not None:
                    roll_spacing = random.random()
                    if roll_spacing < 0.75:
                        ts = max(ts, last_ts + timedelta(minutes=random.randint(125, 600)))
                    elif roll_spacing < 0.90:
                        ts = max(ts, last_ts + timedelta(minutes=random.randint(5, 90)))
                    else:
                        ts = max(ts, last_ts + timedelta(minutes=random.randint(95, 130)))
                now_utc = datetime.utcnow()
                if ts >= now_utc:
                    ts = now_utc - timedelta(minutes=random.randint(2, 180))
                last_planned_ts_by_user_song[spacing_key] = ts
                days_counter[days_ago] += 1

                roll_duration = random.random()
                if roll_duration < 0.05:
                    duration = random.randint(5, 25)
                elif roll_duration < 0.75:
                    duration = random.randint(30, 180)
                else:
                    duration = int(full_track_lengths[song_id])

                try:
                    kwargs = {
                        "db": db,
                        "user_id": user.id,
                        "song_id": song_id,
                        "duration": duration,
                        "idempotency_key": str(uuid.uuid4()),
                    }
                    if supports_event_timestamp:
                        kwargs["event_timestamp"] = ts
                    out = service.process_stream(**kwargs)
                except Exception as exc:
                    failed += 1
                    if len(error_samples) < 5:
                        error_samples.append(f"process_stream failed: {repr(exc)}")
                    continue

                if not isinstance(out, dict) or out.get("status") != "ok":
                    failed += 1
                    if len(error_samples) < 5:
                        error_samples.append(f"unexpected process_stream response: {out}")
                    continue

                event_id = out.get("event_id")
                if not event_id:
                    failed += 1
                    if len(error_samples) < 5:
                        error_samples.append(f"missing event_id in response: {out}")
                    continue

                inserted += 1
                try:
                    process_listening_event(int(event_id))
                except Exception as exc:
                    worker_failures += 1
                    if len(error_samples) < 5:
                        error_samples.append(f"worker failed event {event_id}: {repr(exc)}")
    finally:
        db.close()

    return {
        "inserted": inserted,
        "failed": failed,
        "worker_failures": worker_failures,
        "error_samples": error_samples,
        "days_counter": dict(days_counter),
        "supports_timestamp": supports_event_timestamp,
    }


def _seed_base_data(*, reset: bool, seed: int) -> tuple[list[User], list, list]:
    random.seed(seed)
    ensure_schema()
    if reset:
        reset_existing_data()
    users = _upsert_users()
    artists = _upsert_artists()
    songs = _upsert_songs(artists)
    _set_user_balances(users, amount=10.0)
    # V2 payout line generation requires treasury system entities.
    db = SessionLocal()
    try:
        ensure_treasury_entities(db)
    finally:
        db.close()
    return users, artists, songs


def _insert_event(service: StreamService, *, user_id: int, song_id: int, duration: int) -> None:
    db = SessionLocal()
    try:
        out = service.process_stream(
            db,
            user_id,
            song_id,
            duration,
            idempotency_key=str(uuid.uuid4()),
        )
    finally:
        db.close()
    if not isinstance(out, dict) or out.get("status") != "ok":
        raise RuntimeError(f"edge scenario process_stream: {out}")
    event_id = out.get("event_id")
    if not event_id:
        raise RuntimeError("missing event_id in edge scenario")
    process_listening_event(int(event_id))


def _run_edge_scenario_events(name: str, users: list[User], songs: list) -> None:
    service = StreamService()
    u0 = users[0]
    u1 = users[1]
    s = [int(song.id) for song in songs]

    if name == "zero_listens_user":
        # user0 intentionally has no events; user1 has enough valid events.
        for _ in range(30):
            _insert_event(service, user_id=int(u1.id), song_id=s[2], duration=180)
        return

    if name == "single_song_dominance":
        for _ in range(40):
            _insert_event(service, user_id=int(u0.id), song_id=s[0], duration=180)
        for _ in range(15):
            _insert_event(service, user_id=int(u1.id), song_id=s[3], duration=140)
        return

    if name == "equal_distribution":
        seq = [s[0], s[1], s[2], s[3]]
        for i in range(80):
            _insert_event(service, user_id=int(u0.id), song_id=seq[i % len(seq)], duration=150)
        for i in range(40):
            _insert_event(service, user_id=int(u1.id), song_id=seq[(i + 1) % len(seq)], duration=150)
        return

    if name == "heavy_repeat_user":
        for _ in range(120):
            _insert_event(service, user_id=int(u0.id), song_id=s[4], duration=180)
        for _ in range(50):
            _insert_event(service, user_id=int(u1.id), song_id=s[5], duration=160)
        return

    raise RuntimeError(f"Unknown edge scenario: {name}")


def _build_snapshot(policy_id: str = "v1") -> int:
    db = SessionLocal()
    try:
        min_ts = db.query(func.min(ListeningEvent.timestamp)).scalar()
        max_ts = db.query(func.max(ListeningEvent.timestamp)).scalar()

        if min_ts is None or max_ts is None:
            raise RuntimeError("No events found")

        period_start = min_ts - timedelta(seconds=1)
        period_end = max_ts + timedelta(seconds=1)

        batch = PayoutBatch(
            period_start_at=period_start,
            period_end_at=period_end,
            status="draft",
            currency="USD",
            calculation_version="v2",
            antifraud_version=f"policy:{policy_id}",
        )

        db.add(batch)
        db.commit()
        db.refresh(batch)

        batch_id = int(batch.id)

    finally:
        db.close()

    build_snapshot(
        batch_id=batch_id,
        period_start_at=period_start,
        period_end_at=period_end,
        policy_id=policy_id,
    )

    inserted = int(generate_payout_lines(batch_id, auto_run_settlement=False))
    print(
        f"[PAYOUT LINES GENERATED] batch_id={batch_id} policy_id={policy_id} "
        f"inserted_lines={inserted}"
    )

    return batch_id


def _run_v1_vs_v2_parity(users: list[User], batch_id: int) -> dict[str, object]:
    print("\n=== V1 vs V2 PARITY TEST ===")

    db = SessionLocal()
    try:
        per_user_results: dict[int, dict[str, object]] = {}
        run_max_delta = 0
        run_total_delta = 0
        for user in users:
            # V1
            v1_rows = calculate_user_distribution(user.id)

            v1_cents_by_song: dict[int, int] = {}
            for row in v1_rows:
                sid = int(row["song_id"])
                cents = int(row.get("cents") or 0)
                v1_cents_by_song[sid] = v1_cents_by_song.get(sid, 0) + cents

            v1_total = sum(v1_cents_by_song.values())

            # V2
            v2 = compare_models_v2_snapshot(db, batch_id, user.id)

            v2_cents_by_song = {
                int(k): int(v)
                for k, v in (v2.get("user_cents_by_song") or {}).items()
            }

            v2_total = int(v2.get("total_user_pool_cents") or 0)
            v2_mode = str(v2.get("mode") or "treasury")

            # Normalize V1 mode
            v1_mode = _normalize_v1_mode(v1_rows)

            # TOTAL CHECK (MUST MATCH)
            assert v1_total == v2_total, f"Total mismatch for user {user.id}"

            # MODE CHECK
            assert v1_mode == v2_mode, f"Mode mismatch for user {user.id}: {v1_mode} vs {v2_mode}"

            # PER SONG DIFF
            all_song_ids = sorted(set(v1_cents_by_song) | set(v2_cents_by_song))

            deltas: dict[int, int] = {}
            for sid in all_song_ids:
                d = v2_cents_by_song.get(sid, 0) - v1_cents_by_song.get(sid, 0)
                deltas[sid] = d

            max_delta = max([abs(d) for d in deltas.values()] or [0])
            total_delta = sum(abs(d) for d in deltas.values())
            run_max_delta = max(run_max_delta, int(max_delta))
            run_total_delta = max(run_total_delta, int(total_delta))

            # TOLERANCE CHECK
            assert max_delta <= 1, f"Large per-song delta for user {user.id}"
            assert total_delta <= 5, f"Too much drift for user {user.id}"

            # DEBUG OUTPUT
            print(f"\n--- user_id={user.id} ({user.username}) ---")
            print(f"mode: V1={v1_mode} | V2={v2_mode}")
            print(f"total: V1={v1_total} | V2={v2_total}")
            print("song_id | v1 | v2 | delta")

            for sid in all_song_ids:
                print(
                    f"{sid} | {v1_cents_by_song.get(sid,0)} | "
                    f"{v2_cents_by_song.get(sid,0)} | {deltas[sid]}"
                )

            print(f"max_delta={max_delta} | total_delta={total_delta}")
            per_user_results[int(user.id)] = {
                "v1_mode": v1_mode,
                "v2_mode": v2_mode,
                "v1_total": int(v1_total),
                "v2_total": int(v2_total),
                "max_delta": int(max_delta),
                "total_delta": int(total_delta),
                "v1_cents_by_song": dict(sorted(v1_cents_by_song.items())),
                "v2_cents_by_song": dict(sorted(v2_cents_by_song.items())),
            }

        return {
            "max_delta": int(run_max_delta),
            "total_delta": int(run_total_delta),
            "per_user": per_user_results,
        }
    finally:
        db.close()


def _policy_user_artist_totals(
    db, users: list[User], batch_id: int
) -> tuple[dict[int, dict[int, int]], dict[int, int]]:
    song_artist_rows = db.query(Song.id, Song.artist_id).all()
    song_to_artist = {int(sid): int(aid) for sid, aid in song_artist_rows if aid is not None}

    per_user_artist: dict[int, dict[int, int]] = {}
    artist_totals: dict[int, int] = defaultdict(int)
    for user in users:
        result = compare_models_v2_snapshot(db, int(batch_id), int(user.id))
        cents_by_song = {
            int(sid): int(cents)
            for sid, cents in (result.get("user_cents_by_song") or {}).items()
        }
        user_artist: dict[int, int] = defaultdict(int)
        for song_id, cents in cents_by_song.items():
            artist_id = song_to_artist.get(int(song_id))
            if artist_id is None:
                continue
            user_artist[int(artist_id)] += int(cents)
            artist_totals[int(artist_id)] += int(cents)
        per_user_artist[int(user.id)] = dict(sorted(user_artist.items()))
    return per_user_artist, dict(sorted(artist_totals.items()))


def _run_multi_policy_comparison(users: list[User], policy_to_batch_id: dict[str, int]) -> None:
    print("\n=== MULTI-POLICY COMPARISON ===")
    ordered_policies = [pid for pid in ["v1", "v2_test_A", "v2_test_B"] if pid in policy_to_batch_id]
    if len(ordered_policies) < 2:
        print("Not enough policies to compare.")
        return

    db = SessionLocal()
    try:
        policy_user_song: dict[str, dict[int, dict[int, int]]] = {}
        policy_artist_totals: dict[str, dict[int, int]] = {}
        for policy_id in ordered_policies:
            batch_id = int(policy_to_batch_id[policy_id])
            by_user_song: dict[int, dict[int, int]] = {}
            for user in users:
                result = compare_models_v2_snapshot(db, batch_id, int(user.id))
                by_user_song[int(user.id)] = {
                    int(sid): int(cents)
                    for sid, cents in (result.get("user_cents_by_song") or {}).items()
                }
            policy_user_song[policy_id] = by_user_song
            _, artist_totals = _policy_user_artist_totals(db, users, batch_id)
            policy_artist_totals[policy_id] = artist_totals

        base = "v1"
        for policy_id in ordered_policies:
            if policy_id == base:
                continue
            print(f"\n-- Policy delta {base} -> {policy_id} --")
            print("Per-song deltas by user (target - base):")
            for user in users:
                uid = int(user.id)
                base_map = policy_user_song[base].get(uid, {})
                tgt_map = policy_user_song[policy_id].get(uid, {})
                all_song_ids = sorted(set(base_map.keys()) | set(tgt_map.keys()))
                deltas = {
                    sid: int(tgt_map.get(sid, 0) - base_map.get(sid, 0))
                    for sid in all_song_ids
                }
                print(f"  user_id={uid} {user.username}: {deltas}")

            base_artist = policy_artist_totals[base]
            tgt_artist = policy_artist_totals[policy_id]
            all_artist_ids = sorted(set(base_artist.keys()) | set(tgt_artist.keys()))
            artist_deltas = {
                aid: int(tgt_artist.get(aid, 0) - base_artist.get(aid, 0))
                for aid in all_artist_ids
            }
            print(f"Per-artist deltas (target - base): {artist_deltas}")
    finally:
        db.close()


def _run_one_random_case(seed: int, event_count: int) -> dict[str, object]:
    users, artists, songs = _seed_base_data(reset=True, seed=seed)
    sim = _simulate_events(users, songs, total_events=event_count)
    stats = _collect_validity_stats()
    batch_id = _build_snapshot(policy_id="v1")
    parity = _run_v1_vs_v2_parity(users, batch_id)
    policy_to_batch_id = {"v1": batch_id}
    for policy_id in ["v2_test_A", "v2_test_B"]:
        policy_to_batch_id[policy_id] = _build_snapshot(policy_id=policy_id)
    _run_multi_policy_comparison(users, policy_to_batch_id)
    return {
        "type": "random",
        "seed": seed,
        "events": event_count,
        "sim": sim,
        "stats": stats,
        "parity": parity,
        "policy_batches": policy_to_batch_id,
    }


def _run_edge_case(name: str) -> dict[str, object]:
    users, artists, songs = _seed_base_data(reset=True, seed=1234)
    if name == "zero_listens_user":
        db = SessionLocal()
        try:
            z = db.query(User).filter(User.username == "listener_zero").first()
            if z is None:
                z = create_user(
                    db,
                    "listener_zero@test.local",
                    SEED_LISTENER_PLACEHOLDER_PASSWORD,
                    "listener_zero",
                    username="listener_zero",
                )
            bal = db.query(UserBalance).filter(UserBalance.user_id == z.id).first()
            if bal is None:
                db.add(UserBalance(user_id=z.id, monthly_amount=10.0))
            else:
                bal.monthly_amount = 10.0
            db.commit()
            db.refresh(z)
            users = users + [z]
        finally:
            db.close()

    _run_edge_scenario_events(name, users, songs)
    stats = _collect_validity_stats()
    batch_id = _build_snapshot(policy_id="v1")
    parity = _run_v1_vs_v2_parity(users, batch_id)
    policy_to_batch_id = {"v1": batch_id}
    for policy_id in ["v2_test_A", "v2_test_B"]:
        policy_to_batch_id[policy_id] = _build_snapshot(policy_id=policy_id)
    _run_multi_policy_comparison(users, policy_to_batch_id)

    # Scenario-specific expectations
    if name == "zero_listens_user":
        db = SessionLocal()
        try:
            z = db.query(User).filter(User.username == "listener_zero").one()
            v1_rows = calculate_user_distribution(int(z.id))
            v2 = compare_models_v2_snapshot(db, int(batch_id), int(z.id))
            v1_mode = _normalize_v1_mode(v1_rows)
            assert v1_mode == "treasury", "Zero-listens V1 must be treasury"
            assert str(v2.get("mode") or "") == "treasury", "Zero-listens V2 must be treasury"
            v1_total = int(sum(int(r.get("cents") or 0) for r in v1_rows))
            v2_total = int(v2.get("total_user_pool_cents") or 0)
            assert v1_total == v2_total, "Zero-listens total mismatch"
        finally:
            db.close()
    elif name == "single_song_dominance":
        u = users[0]
        u_result = parity["per_user"][int(u.id)]
        assert len([v for v in u_result["v1_cents_by_song"].values() if int(v) > 0]) == 1
    elif name == "equal_distribution":
        u = users[0]
        u_result = parity["per_user"][int(u.id)]
        vals = [int(v) for v in u_result["v1_cents_by_song"].values() if int(v) > 0]
        assert vals, "Equal distribution scenario empty"
        assert max(vals) - min(vals) <= 1, "Equal distribution drift too large"
    elif name == "heavy_repeat_user":
        # Expect non-trivial weight decay signal.
        assert float(stats["avg_weight"]) < 0.95, "Heavy repeat should reduce average weight"

    return {
        "type": "edge",
        "name": name,
        "stats": stats,
        "parity": parity,
        "policy_batches": policy_to_batch_id,
    }


def _signature_for_result(result: dict[str, object]) -> str:
    parity = result.get("parity", {})
    per_user = parity.get("per_user", {})
    parts: list[str] = []
    for uid in sorted(per_user.keys()):
        row = per_user[uid]
        parts.append(
            f"{uid}:{row['v1_mode']}:{row['v2_mode']}:{row['v1_total']}:{row['v2_total']}:"
            f"{row['v1_cents_by_song']}:{row['v2_cents_by_song']}"
        )
    return "|".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description="V1 vs V2 parity test at cents level.")
    parser.add_argument(
        "--events",
        type=int,
        default=DEFAULT_TOTAL_EVENTS,
        help="Approximate number of events to generate.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducible simulation.",
    )
    parser.add_argument(
        "--no-reset",
        action="store_true",
        help="Do not clear existing data before seeding.",
    )
    args = parser.parse_args()

    # Required harness matrix
    seeds = [1, 7, 42, 99, 123]
    events_grid = [100, 300, 1000]
    edge_cases = [
        "zero_listens_user",
        "single_song_dominance",
        "equal_distribution",
        "heavy_repeat_user",
    ]

    runs: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    worst_max_delta = 0
    worst_total_delta = 0

    print("\n=== EDGE CASE RUNS ===")
    for name in edge_cases:
        try:
            result = _run_edge_case(name)
            runs.append(result)
            parity = result["parity"]
            stats = result["stats"]
            worst_max_delta = max(worst_max_delta, int(parity["max_delta"]))
            worst_total_delta = max(worst_total_delta, int(parity["total_delta"]))
            print(
                f"[PASS] edge={name} valid_pct={stats['valid_pct']:.2f}% "
                f"avg_weight={stats['avg_weight']:.4f} max_delta={parity['max_delta']} "
                f"total_delta={parity['total_delta']}"
            )
        except Exception as exc:
            fail = {"type": "edge", "name": name, "error": repr(exc)}
            failures.append(fail)
            print(f"[FAIL] edge={name} error={repr(exc)}")

    print("\n=== RANDOM MATRIX RUNS ===")
    for seed in seeds:
        for event_count in events_grid:
            try:
                result = _run_one_random_case(seed=seed, event_count=event_count)
                runs.append(result)
                parity = result["parity"]
                stats = result["stats"]
                worst_max_delta = max(worst_max_delta, int(parity["max_delta"]))
                worst_total_delta = max(worst_total_delta, int(parity["total_delta"]))
                print(
                    f"[PASS] seed={seed} events={event_count} valid_pct={stats['valid_pct']:.2f}% "
                    f"avg_weight={stats['avg_weight']:.4f} max_delta={parity['max_delta']} "
                    f"total_delta={parity['total_delta']}"
                )
            except Exception as exc:
                fail = {
                    "type": "random",
                    "seed": seed,
                    "events": event_count,
                    "error": repr(exc),
                }
                failures.append(fail)
                print(f"[FAIL] seed={seed} events={event_count} error={repr(exc)}")

    print("\n=== DETERMINISM CHECK ===")
    try:
        r1 = _run_one_random_case(seed=42, event_count=300)
        r2 = _run_one_random_case(seed=42, event_count=300)
        sig1 = _signature_for_result(r1)
        sig2 = _signature_for_result(r2)
        assert sig1 == sig2, "Determinism mismatch for seed=42 events=300"
        print("[PASS] Determinism seed=42 events=300")
    except Exception as exc:
        failures.append({"type": "determinism", "error": repr(exc)})
        print(f"[FAIL] Determinism error={repr(exc)}")

    total_runs = len(runs) + len([f for f in failures if f["type"] in {"determinism"}])
    passed_runs = len(runs)
    failed_runs = len(failures)
    print("\n=== HARNESS SUMMARY ===")
    print(f"total_runs={total_runs} passed={passed_runs} failed={failed_runs}")
    print(f"worst_max_delta={worst_max_delta} worst_total_delta={worst_total_delta}")

    if failures:
        print("\n=== FAILURE DEBUG BLOCKS ===")
        for fail in failures:
            print(f"- {fail}")
        raise RuntimeError("V1 vs V2 multi-run parity harness failed")


if __name__ == "__main__":
    main()
