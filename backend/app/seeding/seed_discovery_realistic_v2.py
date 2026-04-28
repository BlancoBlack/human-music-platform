"""
Realistic discovery + listening + V2 payout seed (20 artists × 5 songs, 20 users).

Run from backend root:

    python -m app.seeding.seed_discovery_realistic_v2

Or:

    python app/seeding/seed_discovery_realistic_v2.py
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import os
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Sequence

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parents[2]

logging.basicConfig(level=logging.INFO)


def _load_backend_env() -> None:
    env_path = PROJECT_ROOT / ".env"
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path)
        load_dotenv()
    except ImportError:
        if not env_path.is_file():
            return
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            if not key:
                continue
            val = val.strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                val = val[1:-1]
            if key not in os.environ:
                os.environ[key] = val


_load_backend_env()

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import SessionLocal  # noqa: E402
from app.models.artist import Artist  # noqa: E402
from app.models.global_listening_aggregate import GlobalListeningAggregate  # noqa: E402
from app.models.listening_event import ListeningEvent  # noqa: E402
from app.models.payout_batch import PayoutBatch  # noqa: E402
from app.models.payout_line import PayoutLine  # noqa: E402
from app.models.release_media_asset import (  # noqa: E402
    RELEASE_MEDIA_ASSET_TYPE_COVER_ART,
    ReleaseMediaAsset,
)
from app.models.song import Song  # noqa: E402
from app.models.song_media_asset import (  # noqa: E402
    SONG_MEDIA_KIND_MASTER_AUDIO,
    SongMediaAsset,
)
from app.models.user import User  # noqa: E402
from app.services.payout_service import ensure_treasury_entities  # noqa: E402
from app.services.payout_v2_snapshot_engine import generate_payout_lines  # noqa: E402
from app.services.snapshot_service import build_snapshot  # noqa: E402

from app.seeding.seed_common import (  # noqa: E402
    WALLET_ADDRESS,
    _set_user_balances,
    _simulate_weighted_listening_events,
    _upsert_artists,
    _upsert_songs,
    _upsert_users,
    ensure_schema,
    reset_existing_data,
)

LISTENER_NAMES: tuple[str, ...] = tuple(f"disc_listener_{i:02d}" for i in range(1, 21))
ARTIST_NAMES: tuple[str, ...] = tuple(f"Artist {i}" for i in range(1, 21))
LETTERS: tuple[str, ...] = ("A", "B", "C", "D", "E")

MASTER_PATH = "uploads/songs/seed_master.wav"
COVER_PATH = "uploads/covers/seed_cover.png"


def _discovery_title_artist_pairs(artists: list[Artist]) -> list[tuple[str, int]]:
    """
    100 songs ordered for tier simulation: TOP (first 4 artists), MID (next 6),
    TAIL (last 10). Titles: Track {n}{letter}.
    """
    if len(artists) != 20:
        raise RuntimeError(f"Expected 20 artists, got {len(artists)}")
    by_index = {i: int(artists[i - 1].id) for i in range(1, 21)}
    pairs: list[tuple[str, int]] = []
    for ai in range(1, 5):
        for letter in LETTERS:
            pairs.append((f"Track {ai}{letter}", by_index[ai]))
    for ai in range(5, 11):
        for letter in LETTERS:
            pairs.append((f"Track {ai}{letter}", by_index[ai]))
    for ai in range(11, 21):
        for letter in LETTERS:
            pairs.append((f"Track {ai}{letter}", by_index[ai]))
    if len(pairs) != 100:
        raise RuntimeError(f"Expected 100 title pairs, got {len(pairs)}")
    return pairs


def assign_seed_media(songs: Sequence[Song]) -> None:
    """Set song pipeline fields and upsert master media + release cover rows."""
    db = SessionLocal()
    try:
        for s in songs:
            row = db.query(Song).filter(Song.id == int(s.id)).first()
            if row is None:
                continue
            if row.release_id is None:
                raise RuntimeError(
                    f"Seed lifecycle violation: song {int(row.id)} missing release_id before media stage."
                )
            row.file_path = MASTER_PATH
            row.duration_seconds = 180
            row.upload_status = "ready"
            sid = int(row.id)

            kind = SONG_MEDIA_KIND_MASTER_AUDIO
            path = MASTER_PATH
            mime = "audio/wav"
            sha = hashlib.sha256(f"{sid}:{kind}:{path}".encode()).hexdigest()
            asset = (
                db.query(SongMediaAsset)
                .filter(
                    SongMediaAsset.song_id == sid,
                    SongMediaAsset.kind == kind,
                )
                .first()
            )
            if asset is None:
                db.add(
                    SongMediaAsset(
                        song_id=sid,
                        kind=kind,
                        file_path=path,
                        mime_type=mime,
                        byte_size=2048,
                        sha256=sha,
                    )
                )
            else:
                asset.file_path = path
                asset.mime_type = mime
                asset.byte_size = 2048
                asset.sha256 = sha

            if row.release_id is not None:
                rma = (
                    db.query(ReleaseMediaAsset)
                    .filter(
                        ReleaseMediaAsset.release_id == int(row.release_id),
                        ReleaseMediaAsset.asset_type == RELEASE_MEDIA_ASSET_TYPE_COVER_ART,
                    )
                    .first()
                )
                if rma is None:
                    db.add(
                        ReleaseMediaAsset(
                            release_id=int(row.release_id),
                            asset_type=RELEASE_MEDIA_ASSET_TYPE_COVER_ART,
                            file_path=COVER_PATH,
                        )
                    )
                else:
                    rma.file_path = COVER_PATH
        db.commit()
    finally:
        db.close()


def _ensure_non_system_artists_payout_crypto_fallback() -> None:
    db = SessionLocal()
    try:
        rows = (
            db.query(Artist)
            .filter(Artist.is_system.is_(False))
            .order_by(Artist.id.asc())
            .all()
        )
        changed = False
        for a in rows:
            if (a.payout_method or "").strip().lower() != "crypto":
                a.payout_method = "crypto"
                changed = True
            if not (a.payout_wallet_address or "").strip():
                a.payout_wallet_address = WALLET_ADDRESS
                changed = True
        if changed:
            db.commit()
    finally:
        db.close()


def build_batch_snapshot_and_payout_lines(
    policy_id: str = "v1",
) -> tuple[int, int]:
    db = SessionLocal()
    try:
        min_ts = db.query(func.min(ListeningEvent.timestamp)).scalar()
        max_ts = db.query(func.max(ListeningEvent.timestamp)).scalar()

        if min_ts is None or max_ts is None:
            raise RuntimeError("No listening events found; cannot build payout batch")

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
    inserted = int(
        generate_payout_lines(batch_id, auto_settlement_async=False)
    )
    return batch_id, inserted


def _print_discovery_summary(
    users: list[User],
    artists: list[Artist],
    songs: list[Song],
    batch_id: int,
) -> None:
    db = SessionLocal()
    try:
        n_events = int(db.query(ListeningEvent.id).count() or 0)
        n_lines = (
            int(
                db.query(func.count(PayoutLine.id))
                .filter(PayoutLine.batch_id == batch_id)
                .scalar()
            )
            or 0
        )

        print("\n=== Discovery realistic seed summary ===")
        print(f"Users: {len(users)}")
        print(f"Artists: {len(artists)}")
        print(f"Songs: {len(songs)}")
        print(f"Listening events (rows): {n_events}")
        print(f"Payout batch id: {batch_id}")
        print(f"Payout lines: {n_lines}")

        top_songs = (
            db.query(Song.title, GlobalListeningAggregate.total_duration)
            .join(
                GlobalListeningAggregate,
                GlobalListeningAggregate.song_id == Song.id,
            )
            .order_by(desc(GlobalListeningAggregate.total_duration))
            .limit(5)
            .all()
        )
        print("\nTop 5 most listened songs (global aggregate duration):")
        for title, td in top_songs:
            print(f"  {title!r}: {float(td or 0):.1f}s")

        subq = (
            db.query(
                Song.artist_id.label("aid"),
                func.sum(GlobalListeningAggregate.total_duration).label("listen_sum"),
            )
            .join(
                GlobalListeningAggregate,
                GlobalListeningAggregate.song_id == Song.id,
            )
            .group_by(Song.artist_id)
            .subquery()
        )
        top_artists = (
            db.query(Artist.name, subq.c.listen_sum)
            .join(subq, Artist.id == subq.c.aid)
            .order_by(desc(subq.c.listen_sum))
            .limit(5)
            .all()
        )
        print("\nTop 5 artists by total listens (sum of global aggregate per song):")
        for name, td in top_artists:
            print(f"  {name!r}: {float(td or 0):.1f}s")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed 20 artists × 5 songs, weighted listening, V2 payout (discovery QA)."
    )
    parser.add_argument(
        "--no-reset",
        action="store_true",
        help="Do not clear existing DB rows before seeding.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="RNG seed for reproducible weighted listening simulation.",
    )
    parser.add_argument(
        "--policy-id",
        type=str,
        default="v1",
        help="Economics policy id for build_snapshot (default: v1).",
    )
    args = parser.parse_args()
    rng = random.Random(int(args.seed))

    ensure_schema()
    if not args.no_reset:
        reset_existing_data()

    users = _upsert_users(LISTENER_NAMES)
    artists = _upsert_artists(ARTIST_NAMES)
    pairs = _discovery_title_artist_pairs(artists)
    songs = _upsert_songs(artists, title_artist_id_pairs=pairs)
    assign_seed_media(songs)

    _set_user_balances(users, amount=10.0)

    db_treasury: Session = SessionLocal()
    try:
        ensure_treasury_entities(db_treasury)
        db_treasury.commit()
    finally:
        db_treasury.close()

    _ensure_non_system_artists_payout_crypto_fallback()

    sim = _simulate_weighted_listening_events(
        users,
        songs,
        rng=rng,
        top_n=20,
        mid_n=30,
        tail_n=50,
        tier_weights=(0.6, 0.3, 0.1),
        events_per_user_min=80,
        events_per_user_max=150,
        max_repeat_per_user_song=3,
    )
    print("Event time distribution (days ago -> count):")
    for day in [0, 1, 2, 5, 30, 60]:
        print(f"- {day}: {sim['days_counter'].get(day, 0)}")
    print(f"Inserted events: {sim['inserted']}")
    print(f"Failed events: {sim['failed']}")
    print(f"Worker failures: {sim['worker_failures']}")
    if sim["error_samples"]:
        print("Sample errors:")
        for msg in sim["error_samples"]:
            print(f"- {msg}")

    batch_id, n_lines = build_batch_snapshot_and_payout_lines(policy_id=args.policy_id)
    print(
        f"\n[V2 LEDGER] batch_id={batch_id} policy_id={args.policy_id} "
        f"payout_lines_inserted={n_lines}"
    )

    _print_discovery_summary(users, artists, songs, batch_id)


if __name__ == "__main__":
    main()
