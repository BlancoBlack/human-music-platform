"""
Seed listening data using shared helpers from ``app.seeding.seed_common``.

Creates the small default artist/user/song set, simulates listening events, then
runs the V2 ledger pipeline:

  payout_batch (draft) → build_snapshot → generate_payout_lines

Treasury artist/song are ensured before events (same invariant as parity tests).

There is no separate ``seed_data.py``; this entrypoint relies entirely on
``seed_common`` utilities.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_backend_env() -> None:
    """Match FastAPI's .env loading; works without python-dotenv if package missing."""
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

import argparse
import logging
import random
import wave
from datetime import timedelta

from sqlalchemy import func

from app.core.database import SessionLocal
from app.models.artist import Artist
from app.models.song import Song
from app.models.listening_event import ListeningEvent
from app.models.payout_batch import PayoutBatch
from app.models.payout_line import PayoutLine
from app.services.payout_service import ensure_treasury_entities
from app.services.payout_v2_snapshot_engine import generate_payout_lines
from app.services.snapshot_service import build_snapshot

from app.seeding.seed_common import (
    DEFAULT_TOTAL_EVENTS,
    WALLET_ADDRESS,
    _print_summary,
    _set_user_balances,
    _simulate_events,
    _upsert_artists,
    _upsert_songs,
    _upsert_users,
    ensure_schema,
    reset_existing_data,
)

logger = logging.getLogger(__name__)


def _ensure_treasury_invariants() -> None:
    db = SessionLocal()
    try:
        ensure_treasury_entities(db)
    finally:
        db.close()


def _wav_pcm_duration_from_data_chunk(abs_path: Path) -> float | None:
    """
    Duration from RIFF ``data`` chunk size and ``fmt`` parameters.

    Many tools write an incorrect frame count in the WAV header while the ``data``
    chunk length is correct; this path matches:

        duration = data_size / (sample_rate * n_channels * bytes_per_sample)
    """
    try:
        with abs_path.open("rb") as f:
            if f.read(4) != b"RIFF":
                return None
            f.read(4)
            if f.read(4) != b"WAVE":
                return None
            rate = 0
            nchannels = 0
            sampwidth = 0
            audio_format: int | None = None
            while True:
                tag = f.read(4)
                if len(tag) < 4:
                    break
                size_b = f.read(4)
                if len(size_b) < 4:
                    break
                chunk_size = int.from_bytes(size_b, "little")
                if tag == b"fmt ":
                    raw = f.read(chunk_size)
                    if chunk_size % 2:
                        f.read(1)
                    if len(raw) < 16:
                        continue
                    audio_format = int.from_bytes(raw[0:2], "little")
                    nchannels = int.from_bytes(raw[2:4], "little")
                    rate = int.from_bytes(raw[4:8], "little")
                    bits = int.from_bytes(raw[14:16], "little")
                    sampwidth = max(1, (bits + 7) // 8)
                elif tag == b"data":
                    if audio_format is None or rate <= 0 or nchannels <= 0 or sampwidth <= 0:
                        return None
                    bytes_per_sec = rate * nchannels * sampwidth
                    if bytes_per_sec <= 0:
                        return None
                    return chunk_size / float(bytes_per_sec)
                else:
                    skip = chunk_size + (chunk_size % 2)
                    f.seek(skip, 1)
    except OSError:
        return None
    return None


def _wav_duration_seconds(abs_path: Path) -> float:
    """Duration from WAV: prefer ``data`` chunk size; fall back to ``frames / rate``."""
    filename = abs_path.name
    with wave.open(str(abs_path), "rb") as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        if rate <= 0:
            logger.info(
                "wav_duration_extracted",
                extra={"file": filename, "duration": 0.0},
            )
            return 0.0
        duration_from_frames = frames / float(rate)

    duration_from_data = _wav_pcm_duration_from_data_chunk(abs_path)
    if duration_from_data is not None and duration_from_data > 0:
        duration = duration_from_data
    else:
        duration = duration_from_frames

    logger.info(
        "wav_duration_extracted",
        extra={"file": filename, "duration": duration},
    )
    return duration


def _assign_seed_song_wavs(artists: list[Artist], songs: list[Song]) -> None:
    """
    Point seeded songs at real files under uploads/songs/ and set duration_seconds.

    Artist A songs use ``artist_a__*.wav`` (sorted); Artist B uses ``artist_b__*.wav``.
    Missing or unreadable files are skipped with a warning; seed continues.
    """
    if len(artists) < 2:
        return

    uploads_dir = PROJECT_ROOT / "uploads" / "songs"
    artist_slug_by_id: dict[int, str] = {
        int(artists[0].id): "artist_a",
        int(artists[1].id): "artist_b",
    }
    files_by_slug: dict[str, list[Path]] = {
        "artist_a": sorted(uploads_dir.glob("artist_a__*.wav")),
        "artist_b": sorted(uploads_dir.glob("artist_b__*.wav")),
    }
    counters: dict[str, int] = {"artist_a": 0, "artist_b": 0}

    db = SessionLocal()
    try:
        for song in songs:
            slug = artist_slug_by_id.get(int(song.artist_id))
            if slug is None:
                continue
            paths = files_by_slug[slug]
            idx = counters[slug]
            counters[slug] += 1
            if idx >= len(paths):
                logger.warning(
                    "seed wav: no file for song id=%s title=%s (%s index %s)",
                    song.id,
                    song.title,
                    slug,
                    idx,
                )
                continue
            abs_path = paths[idx]
            if not abs_path.is_file():
                logger.warning("seed wav: missing or not a file: %s", abs_path)
                continue
            try:
                duration_f = _wav_duration_seconds(abs_path)
            except (wave.Error, OSError, EOFError, ValueError) as exc:
                logger.warning("seed wav: cannot read %s: %s", abs_path, exc)
                continue
            if duration_f <= 0:
                logger.warning(
                    "seed wav: zero duration for %s (song id=%s)", abs_path, song.id
                )
                continue

            rel = f"uploads/songs/{abs_path.name}"
            secs = max(1, int(round(duration_f)))
            row = db.query(Song).filter(Song.id == song.id).first()
            if row is None:
                logger.warning("seed wav: song id=%s not found in DB", song.id)
                continue
            row.file_path = rel
            row.duration_seconds = secs
            song.file_path = rel
            song.duration_seconds = secs

        db.commit()
    finally:
        db.close()


def _ensure_non_system_artists_payout_crypto_fallback() -> None:
    """
    Secondary fix for ``--no-reset`` or legacy rows: match seed invariants
    (payout_method=crypto, wallet address set). Primary source of truth is
    ``_upsert_artists()`` in app.seeding.seed_common.
    """
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


def build_batch_snapshot_and_payout_lines(policy_id: str = "v1") -> tuple[int, int]:
    """
    Create a draft PayoutBatch covering all seeded events, seal snapshot, generate lines.

    Returns (batch_id, number of payout_lines inserted).
    """
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


def _print_v2_ledger_summary(batch_id: int) -> None:
    db = SessionLocal()
    try:
        batch = db.query(PayoutBatch).filter(PayoutBatch.id == batch_id).first()
        if batch is None:
            print(f"\n=== V2 ledger summary ===\nBatch {batch_id} not found.")
            return

        n_lines = (
            int(db.query(func.count(PayoutLine.id)).filter(PayoutLine.batch_id == batch_id).scalar())
            or 0
        )

        by_type = (
            db.query(PayoutLine.line_type, func.sum(PayoutLine.amount_cents))
            .filter(PayoutLine.batch_id == batch_id)
            .group_by(PayoutLine.line_type)
            .all()
        )

        print("\n=== V2 ledger summary ===")
        print(
            f"batch_id={batch_id} status={batch.status} "
            f"snapshot_id={batch.snapshot_id} lines={n_lines}"
        )
        print("Amount (cents) by line_type:")
        for line_type, cents in sorted(by_type, key=lambda x: str(x[0])):
            print(f"  {line_type}: {int(cents or 0)}")

        samples = (
            db.query(PayoutLine)
            .filter(PayoutLine.batch_id == batch_id)
            .order_by(PayoutLine.id.asc())
            .limit(5)
            .all()
        )
        if samples:
            print("Sample payout_lines (first 5):")
            for row in samples:
                print(
                    f"  user={row.user_id} song={row.song_id} artist={row.artist_id} "
                    f"cents={row.amount_cents} type={row.line_type}"
                )
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed listening data like seed_data.py, then run V2 batch/snapshot/payout_lines."
    )
    parser.add_argument(
        "--events",
        type=int,
        default=DEFAULT_TOTAL_EVENTS,
        help=f"Approximate number of events to generate (default: {DEFAULT_TOTAL_EVENTS}).",
    )
    parser.add_argument(
        "--no-reset",
        action="store_true",
        help="Do not clear existing users/artists/songs/events before seeding.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducible simulation.",
    )
    parser.add_argument(
        "--policy-id",
        type=str,
        default="v1",
        help="Economics policy id passed to build_snapshot (default: v1).",
    )
    args = parser.parse_args()

    random.seed(args.seed)
    ensure_schema()
    if not args.no_reset:
        reset_existing_data()

    users = _upsert_users()
    artists = _upsert_artists()
    songs = _upsert_songs(artists)
    _assign_seed_song_wavs(artists, songs)
    _set_user_balances(users, amount=10.0)

    _ensure_treasury_invariants()
    _ensure_non_system_artists_payout_crypto_fallback()

    sim = _simulate_events(users, songs, total_events=args.events)
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

    _print_summary(users, artists)
    _print_v2_ledger_summary(batch_id)


if __name__ == "__main__":
    main()
