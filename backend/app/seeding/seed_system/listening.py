from __future__ import annotations

import inspect
import random
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from app.core.database import SessionLocal
from app.models.song import Song
from app.models.user import User
from app.services.stream_service import StreamService
from app.workers.listen_worker import process_listening_event


def simulate_listening(
    *,
    users: list[User],
    songs: list[Song],
    rng_seed: int,
    listens_per_user_min: int,
    listens_per_user_max: int,
    max_repeat_per_user_song: int,
) -> dict[str, object]:
    if not users:
        raise RuntimeError("No users to simulate listening.")
    if not songs:
        raise RuntimeError("No songs to simulate listening.")

    rng = random.Random(rng_seed)
    service = StreamService()
    supports_event_timestamp = "event_timestamp" in inspect.signature(service.process_stream).parameters

    songs_by_artist: dict[int, list[Song]] = defaultdict(list)
    for song in songs:
        songs_by_artist[int(song.artist_id)].append(song)
    artist_ids = sorted(songs_by_artist.keys())
    tier_weights = _artist_tier_weights(artist_ids)

    per_pair_count: dict[tuple[int, int], int] = defaultdict(int)
    last_ts_per_pair: dict[tuple[int, int], datetime] = {}
    inserted = 0
    failed = 0
    duplicates = 0
    worker_failures = 0

    db = SessionLocal()
    try:
        for user in users:
            uid = int(user.id)
            n_events = rng.randint(listens_per_user_min, listens_per_user_max)
            for ordinal in range(1, n_events + 1):
                song = _pick_song(
                    rng=rng,
                    songs_by_artist=songs_by_artist,
                    artist_ids=artist_ids,
                    tier_weights=tier_weights,
                    per_pair_count=per_pair_count,
                    user_id=uid,
                    max_repeat_per_user_song=max_repeat_per_user_song,
                )
                if song is None:
                    failed += 1
                    continue
                sid = int(song.id)
                pair = (uid, sid)
                per_pair_count[pair] += 1
                ts = _build_event_timestamp(rng=rng, previous=last_ts_per_pair.get(pair))
                last_ts_per_pair[pair] = ts
                duration = _sample_duration(rng=rng, max_duration=max(60, int(song.duration_seconds or 180)))
                idempotency_key = f"seed_system_listen:{uid}:{sid}:{ordinal}"
                kwargs = {
                    "db": db,
                    "user_id": uid,
                    "song_id": sid,
                    "duration": duration,
                    "idempotency_key": idempotency_key,
                }
                if supports_event_timestamp:
                    kwargs["event_timestamp"] = ts
                out = service.process_stream(**kwargs)
                status = out.get("status") if isinstance(out, dict) else None
                if status == "duplicate":
                    duplicates += 1
                    continue
                if status != "ok":
                    failed += 1
                    continue
                event_id = out.get("event_id")
                if not event_id:
                    failed += 1
                    continue
                inserted += 1
                try:
                    process_listening_event(int(event_id))
                except Exception:
                    worker_failures += 1
    finally:
        db.close()
    return {
        "inserted": inserted,
        "failed": failed,
        "duplicates": duplicates,
        "worker_failures": worker_failures,
    }


def _artist_tier_weights(artist_ids: list[int]) -> dict[int, float]:
    out: dict[int, float] = {}
    for idx, artist_id in enumerate(artist_ids):
        if idx < 2:
            out[artist_id] = 14.0
        elif idx < 5:
            out[artist_id] = 6.0
        else:
            out[artist_id] = 1.8
    return out


def _pick_song(
    *,
    rng: random.Random,
    songs_by_artist: dict[int, list[Song]],
    artist_ids: list[int],
    tier_weights: dict[int, float],
    per_pair_count: dict[tuple[int, int], int],
    user_id: int,
    max_repeat_per_user_song: int,
) -> Song | None:
    artist_weight_list = [tier_weights[artist_id] for artist_id in artist_ids]
    for _ in range(60):
        artist_id = int(rng.choices(artist_ids, weights=artist_weight_list, k=1)[0])
        song = rng.choice(songs_by_artist[artist_id])
        if per_pair_count[(user_id, int(song.id))] < max_repeat_per_user_song:
            return song
    return None


def _build_event_timestamp(*, rng: random.Random, previous: datetime | None) -> datetime:
    now = datetime.now(UTC).replace(tzinfo=None)
    if previous is None:
        days_ago = int(rng.choices([0, 1, 2, 3, 7, 14, 30], weights=[24, 20, 17, 12, 11, 10, 6], k=1)[0])
        ts = now - timedelta(days=days_ago, hours=rng.randint(0, 23), minutes=rng.randint(0, 59))
    else:
        ts = previous + timedelta(minutes=rng.randint(30, 600))
    if ts >= now:
        ts = now - timedelta(minutes=rng.randint(5, 180))
    return ts


def _sample_duration(*, rng: random.Random, max_duration: int) -> int:
    roll = rng.random()
    if roll < 0.08:
        return rng.randint(25, 55)
    if roll < 0.72:
        low = max(55, int(max_duration * 0.35))
        return rng.randint(low, max_duration)
    return max_duration
