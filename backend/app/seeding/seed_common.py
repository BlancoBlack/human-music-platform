from __future__ import annotations

import inspect
import random
import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timedelta

from sqlalchemy import text

from app.core.database import Base, SessionLocal, engine
from app.core.sqlite_compat import (
    ensure_auth_user_schema,
    ensure_refresh_token_schema,
    ensure_song_credit_entries_position_column,
)
from app.models.artist import Artist
from app.models.global_listening_aggregate import GlobalListeningAggregate
from app.models.listening_aggregate import ListeningAggregate
from app.models.listening_event import ListeningEvent
from app.models.listening_session import ListeningSession
from app.models.payout_batch import PayoutBatch
from app.models.payout_input_snapshot import PayoutInputSnapshot
from app.models.payout_line import PayoutLine
from app.models.payout_settlement import PayoutSettlement
from app.models.snapshot_listening_input import SnapshotListeningInput
from app.models.snapshot_user_pool import SnapshotUserPool
from app.models.song import Song
from app.models.song_artist_split import SongArtistSplit
from app.models.song_credit_entry import SongCreditEntry
from app.models.song_featured_artist import SongFeaturedArtist
from app.models.song_media_asset import SongMediaAsset
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.models.user_balance import UserBalance
from app.models.user_profile import UserProfile
from app.models.user_role import UserRole
from app.services.stream_service import StreamService
from app.services.user_service import (
    SEED_LISTENER_PLACEHOLDER_PASSWORD,
    create_user,
)
from app.workers.listen_worker import process_listening_event

DEFAULT_TOTAL_EVENTS = 5000
WALLET_ADDRESS = "APQVRSIZTCOOHLVLFOTZAEFPO3VNA5DHXBQNGUQARQP2EBWWLDMKUMNKIA"
_LEGACY_SEED_WALLET_PLACEHOLDER = "SEED_ARTIST_WALLET_PLACEHOLDER"

_USER_NAMES = ("listener_1", "listener_2")
_ARTIST_NAMES = ("Artist A", "Artist B")
_SONG_TITLES = (
    "Track A1",
    "Track A2",
    "Track A3",
    "Track B1",
    "Track B2",
    "Track B3",
)


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    rows = conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return any(row[1] == column_name for row in rows)


def _sqlite_table_exists(conn, table_name: str) -> bool:
    row = conn.execute(
        text("SELECT 1 FROM sqlite_master WHERE type='table' AND name = :n LIMIT 1"),
        {"n": table_name},
    ).fetchone()
    return row is not None


def _ensure_sqlite_compat_columns() -> None:
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as conn:
        if _sqlite_table_exists(conn, "payout_settlements"):
            if not _column_exists(conn, "payout_settlements", "splits_digest"):
                conn.execute(
                    text("ALTER TABLE payout_settlements ADD COLUMN splits_digest VARCHAR(64)")
                )
            if not _column_exists(conn, "payout_settlements", "destination_wallet"):
                conn.execute(
                    text(
                        "ALTER TABLE payout_settlements ADD COLUMN destination_wallet VARCHAR(255)"
                    )
                )

        if _sqlite_table_exists(conn, "artists") and not _column_exists(
            conn, "artists", "system_key"
        ):
            conn.execute(text("ALTER TABLE artists ADD COLUMN system_key VARCHAR(64)"))
        if _sqlite_table_exists(conn, "songs") and not _column_exists(
            conn, "songs", "system_key"
        ):
            conn.execute(text("ALTER TABLE songs ADD COLUMN system_key VARCHAR(64)"))

        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_artists_system_key "
                "ON artists(system_key) WHERE system_key IS NOT NULL"
            )
        )
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_songs_system_key "
                "ON songs(system_key) WHERE system_key IS NOT NULL"
            )
        )


def ensure_schema() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_song_credit_entries_position_column(engine)
    ensure_auth_user_schema(engine)
    ensure_refresh_token_schema(engine)
    _ensure_sqlite_compat_columns()


def reset_existing_data() -> None:
    db = SessionLocal()
    try:
        # Break circular FK: payout_batches.snapshot_id -> payout_input_snapshots.id
        # and snapshots.batch_id -> payout_batches.id (delete children first).
        db.query(PayoutSettlement).delete(synchronize_session=False)
        db.query(PayoutLine).delete(synchronize_session=False)
        db.query(SnapshotListeningInput).delete(synchronize_session=False)
        db.query(SnapshotUserPool).delete(synchronize_session=False)
        db.query(PayoutBatch).update(
            {PayoutBatch.snapshot_id: None},
            synchronize_session=False,
        )
        db.flush()
        db.query(PayoutInputSnapshot).delete(synchronize_session=False)
        db.query(PayoutBatch).delete(synchronize_session=False)
        db.query(ListeningAggregate).delete(synchronize_session=False)
        db.query(GlobalListeningAggregate).delete(synchronize_session=False)
        db.query(ListeningEvent).delete(synchronize_session=False)
        db.query(ListeningSession).delete(synchronize_session=False)
        db.query(SongArtistSplit).delete(synchronize_session=False)
        db.query(SongFeaturedArtist).delete(synchronize_session=False)
        db.query(SongCreditEntry).delete(synchronize_session=False)
        db.query(SongMediaAsset).delete(synchronize_session=False)
        db.query(Song).delete(synchronize_session=False)
        db.query(UserBalance).delete(synchronize_session=False)
        db.query(RefreshToken).delete(synchronize_session=False)
        db.query(UserProfile).delete(synchronize_session=False)
        db.query(UserRole).delete(synchronize_session=False)
        db.query(Artist).delete(synchronize_session=False)
        db.query(User).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def _upsert_users(usernames: Sequence[str] | None = None) -> list[User]:
    """Create or load users by username. Defaults to ``_USER_NAMES`` when omitted."""
    names: tuple[str, ...] = tuple(usernames) if usernames is not None else _USER_NAMES
    db = SessionLocal()
    out: list[User] = []
    try:
        for name in names:
            user = db.query(User).filter(User.username == name).first()
            if user is None:
                user = create_user(
                    db,
                    f"{name}@seed.local",
                    SEED_LISTENER_PLACEHOLDER_PASSWORD,
                    display_name=name,
                    username=name,
                )
            out.append(user)
        db.commit()
        for u in out:
            db.refresh(u)
        return out
    finally:
        db.close()


def _upsert_artists(artist_names: Sequence[str] | None = None) -> list[Artist]:
    """Create or load artists by name. Defaults to ``_ARTIST_NAMES`` when omitted."""
    names: tuple[str, ...] = tuple(artist_names) if artist_names is not None else _ARTIST_NAMES
    db = SessionLocal()
    out: list[Artist] = []
    try:
        for idx, name in enumerate(names, start=1):
            artist = db.query(Artist).filter(Artist.name == name).first()
            if artist is None:
                artist = Artist(name=name)
                db.add(artist)
                db.flush()
            artist.payout_method = "crypto"
            current_wallet = (artist.payout_wallet_address or "").strip()
            if (not current_wallet) or (current_wallet == _LEGACY_SEED_WALLET_PLACEHOLDER):
                artist.payout_wallet_address = WALLET_ADDRESS
            if not (artist.system_key or "").strip():
                artist.system_key = f"seed.artist.{idx}"
            out.append(artist)
        db.commit()
        for a in out:
            db.refresh(a)
        return out
    finally:
        db.close()


def _upsert_songs(
    artists: list[Artist],
    *,
    title_artist_id_pairs: Sequence[tuple[str, int]] | None = None,
) -> list[Song]:
    """
    Create or load songs.

    Default mode (``title_artist_id_pairs`` omitted) requires at least two artists
    and uses ``_SONG_TITLES`` split across the first two artists (legacy seed).

    Discovery / custom seeds may pass explicit ``(title, artist_id)`` rows; then
    only ``len(artists) >= 1`` is required and every ``artist_id`` must belong to
    ``artists``.
    """
    db = SessionLocal()
    out: list[Song] = []
    try:
        artist_ids_set = {int(a.id) for a in artists}
        if title_artist_id_pairs is None:
            if len(artists) < 2:
                raise RuntimeError("Expected at least two artists for default seed songs")
            artist_ids = [int(a.id) for a in artists]
            for idx, title in enumerate(_SONG_TITLES, start=1):
                artist_id = artist_ids[0] if idx <= 3 else artist_ids[1]
                song = db.query(Song).filter(Song.title == title).first()
                if song is None:
                    song = Song(title=title, artist_id=artist_id)
                    db.add(song)
                    db.flush()
                else:
                    song.artist_id = artist_id
                if not (song.system_key or "").strip():
                    song.system_key = f"seed.song.{idx}"
                out.append(song)
        else:
            if not artists:
                raise RuntimeError("Expected at least one artist for custom seed songs")
            for idx, (title, artist_id) in enumerate(title_artist_id_pairs, start=1):
                aid = int(artist_id)
                if aid not in artist_ids_set:
                    raise RuntimeError(f"artist_id {aid} not in seed artist list for title {title!r}")
                song = db.query(Song).filter(Song.title == title).first()
                if song is None:
                    song = Song(title=title, artist_id=aid)
                    db.add(song)
                    db.flush()
                else:
                    song.artist_id = aid
                if not (song.system_key or "").strip():
                    song.system_key = f"seed.song.{idx}"
                out.append(song)
        db.commit()
        for s in out:
            db.refresh(s)
        return out
    finally:
        db.close()


def _set_user_balances(users: list[User], amount: float = 10.0) -> None:
    db = SessionLocal()
    try:
        for user in users:
            bal = db.query(UserBalance).filter(UserBalance.user_id == int(user.id)).first()
            if bal is None:
                bal = UserBalance(user_id=int(user.id), monthly_amount=float(amount))
                db.add(bal)
            else:
                bal.monthly_amount = float(amount)
        db.commit()
    finally:
        db.close()


def _pick_days_ago() -> int:
    days = [0, 1, 2, 5, 30, 60]
    weights = [0.28, 0.22, 0.20, 0.14, 0.10, 0.06]
    return int(random.choices(days, weights=weights, k=1)[0])


def _timestamp_for_days_ago(days_ago: int) -> datetime:
    now_utc = datetime.utcnow()
    ts = now_utc - timedelta(
        days=int(days_ago),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59),
        seconds=random.randint(0, 59),
    )
    if ts >= now_utc:
        ts = now_utc - timedelta(minutes=random.randint(1, 30))
    return ts


def _random_duration() -> int:
    roll = random.random()
    if roll < 0.05:
        return random.randint(5, 25)
    if roll < 0.75:
        return random.randint(30, 180)
    return random.randint(190, 320)


def _simulate_events(users: list[User], songs: list[Song], total_events: int) -> dict[str, object]:
    service = StreamService()
    supports_event_timestamp = "event_timestamp" in inspect.signature(
        service.process_stream
    ).parameters

    if len(users) < 2:
        raise RuntimeError("Expected at least two users for seeded simulation")
    if len(songs) < 6:
        raise RuntimeError("Expected at least six songs for seeded simulation")

    u1_weights = [0.30, 0.26, 0.20, 0.14, 0.06, 0.04]
    u2_weights = [0.05, 0.08, 0.25, 0.24, 0.19, 0.19]
    song_ids = [int(s.id) for s in songs[:6]]
    full_track_lengths: dict[int, int] = {}
    for s in songs[:6]:
        sid = int(s.id)
        ds = getattr(s, "duration_seconds", None)
        if ds is not None and int(ds) > 0:
            full_track_lengths[sid] = int(ds)
        else:
            full_track_lengths[sid] = random.randint(190, 320)

    user_event_targets = {
        int(users[0].id): int(total_events * 0.55),
        int(users[1].id): total_events - int(total_events * 0.55),
    }

    last_planned_ts_by_user_song: dict[tuple[int, int], datetime] = {}
    days_counter: dict[int, int] = defaultdict(int)
    inserted = 0
    failed = 0
    worker_failures = 0
    error_samples: list[str] = []
    db = SessionLocal()
    try:
        for user in users[:2]:
            user_id = int(user.id)
            weights = u1_weights if user_id == int(users[0].id) else u2_weights
            for _ in range(user_event_targets[user_id]):
                days_ago = _pick_days_ago()
                song_id = int(random.choices(song_ids, weights=weights, k=1)[0])
                ts = _timestamp_for_days_ago(days_ago)
                spacing_key = (user_id, song_id)

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
                        "user_id": user_id,
                        "song_id": song_id,
                        "duration": int(duration),
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


def _simulate_weighted_listening_events(
    users: list[User],
    songs_ordered: list[Song],
    *,
    rng: random.Random,
    top_n: int = 20,
    mid_n: int = 30,
    tail_n: int = 50,
    tier_weights: tuple[float, float, float] = (0.6, 0.3, 0.1),
    events_per_user_min: int = 80,
    events_per_user_max: int = 150,
    max_repeat_per_user_song: int = 3,
) -> dict[str, object]:
    """
    Insert listening events for many users with tiered song popularity (TOP/MID/TAIL).

    Reuses ``_pick_days_ago`` / ``_timestamp_for_days_ago`` and the same
    ``StreamService.process_stream`` + ``process_listening_event`` path as
    ``_simulate_events``.

    ``songs_ordered`` must be ordered so the first ``top_n`` ids are TOP tier,
    next ``mid_n`` are MID, remainder TAIL (defaults 20/30/50 for 100 songs).
    """
    service = StreamService()
    supports_event_timestamp = "event_timestamp" in inspect.signature(
        service.process_stream
    ).parameters

    if not users:
        raise RuntimeError("Expected at least one user for weighted simulation")
    if not songs_ordered:
        raise RuntimeError("Expected at least one song for weighted simulation")

    n = len(songs_ordered)
    tn = min(top_n, n)
    mn = min(mid_n, max(0, n - tn))
    tail_count = max(0, n - tn - mn)
    top_songs = songs_ordered[:tn]
    mid_songs = songs_ordered[tn : tn + mn]
    tail_songs = songs_ordered[tn + mn : tn + mn + tail_count]

    top_ids = [int(s.id) for s in top_songs]
    mid_ids = [int(s.id) for s in mid_songs]
    tail_ids = [int(s.id) for s in tail_songs]
    all_ids = top_ids + mid_ids + tail_ids
    tiers = (top_ids, mid_ids, tail_ids)

    full_track_lengths: dict[int, int] = {}
    for s in songs_ordered:
        sid = int(s.id)
        ds = getattr(s, "duration_seconds", None)
        if ds is not None and int(ds) > 0:
            full_track_lengths[sid] = int(ds)
        else:
            full_track_lengths[sid] = 180

    user_song_counts: defaultdict[tuple[int, int], int] = defaultdict(int)

    def _pick_song_id(user_id: int) -> int | None:
        for _ in range(80):
            tier_idx = rng.choices([0, 1, 2], weights=list(tier_weights), k=1)[0]
            pool = tiers[tier_idx]
            if not pool:
                continue
            sid = int(rng.choice(pool))
            if user_song_counts[(user_id, sid)] < max_repeat_per_user_song:
                return sid
        for sid in all_ids:
            if user_song_counts[(user_id, int(sid))] < max_repeat_per_user_song:
                return int(sid)
        return None

    last_planned_ts_by_user_song: dict[tuple[int, int], datetime] = {}
    days_counter: dict[int, int] = defaultdict(int)
    inserted = 0
    failed = 0
    worker_failures = 0
    error_samples: list[str] = []

    db = SessionLocal()
    try:
        for user in users:
            user_id = int(user.id)
            n_events = rng.randint(events_per_user_min, events_per_user_max)
            for _ in range(n_events):
                song_id = _pick_song_id(user_id)
                if song_id is None:
                    failed += 1
                    continue

                days_ago = _pick_days_ago()
                ts = _timestamp_for_days_ago(days_ago)
                spacing_key = (user_id, song_id)

                last_ts = last_planned_ts_by_user_song.get(spacing_key)
                if last_ts is not None:
                    roll_spacing = rng.random()
                    if roll_spacing < 0.75:
                        ts = max(
                            ts,
                            last_ts + timedelta(minutes=rng.randint(125, 600)),
                        )
                    elif roll_spacing < 0.90:
                        ts = max(
                            ts,
                            last_ts + timedelta(minutes=rng.randint(5, 90)),
                        )
                    else:
                        ts = max(
                            ts,
                            last_ts + timedelta(minutes=rng.randint(95, 130)),
                        )
                now_utc = datetime.utcnow()
                if ts >= now_utc:
                    ts = now_utc - timedelta(minutes=rng.randint(2, 180))

                last_planned_ts_by_user_song[spacing_key] = ts
                days_counter[days_ago] += 1

                roll_duration = rng.random()
                cap = full_track_lengths.get(song_id, 180)
                if roll_duration < 0.05:
                    duration = rng.randint(55, min(90, cap))
                elif roll_duration < 0.75:
                    duration = rng.randint(max(55, int(cap * 0.31)), cap)
                else:
                    duration = int(cap)

                try:
                    kwargs = {
                        "db": db,
                        "user_id": user_id,
                        "song_id": song_id,
                        "duration": int(duration),
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
                user_song_counts[(user_id, song_id)] += 1
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


def _print_summary(users: list[User], artists: list[Artist]) -> None:
    db = SessionLocal()
    try:
        n_events = int(db.query(ListeningEvent.id).count() or 0)
        n_valid = int(db.query(ListeningEvent.id).filter(ListeningEvent.is_valid.is_(True)).count() or 0)
        n_invalid = n_events - n_valid
        balances = (
            db.query(UserBalance.user_id, UserBalance.monthly_amount)
            .order_by(UserBalance.user_id.asc())
            .all()
        )

        print("\n=== Seed summary ===")
        print(f"Users: {len(users)}  Artists: {len(artists)}")
        print(f"Events: {n_events}  Valid: {n_valid}  Invalid: {n_invalid}")
        print("Balances:")
        for user_id, monthly_amount in balances:
            print(f"- user_id={int(user_id)} monthly_amount={float(monthly_amount):.2f}")
    finally:
        db.close()
