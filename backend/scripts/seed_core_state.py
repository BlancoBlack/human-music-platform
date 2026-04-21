#!/usr/bin/env python3
"""
Canonical idempotent core state seed for local development and demos.

Run from ``backend/`` after schema is current::

    alembic upgrade head
    PYTHONPATH=. python scripts/seed_core_state.py

Optional: ``--reset`` clears domain tables (same scope as ``seed_common.reset_existing_data``)
then rebuilds everything.

Identity is keyed by **email** (users), **system_key** (artists/songs) — never by title/name alone.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import inspect
import os
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _load_backend_env() -> None:
    env_path = BACKEND_ROOT / ".env"
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

from app.core.database import SessionLocal  # noqa: E402
from app.models.artist import Artist  # noqa: E402
from app.models.genre import Genre  # noqa: E402
from app.models.listening_event import ListeningEvent  # noqa: E402
from app.models.payout_batch import PayoutBatch  # noqa: E402
from app.models.payout_line import PayoutLine  # noqa: E402
from app.models.song import (  # noqa: E402
    SONG_STATE_READY_FOR_RELEASE,
    Song,
)
from app.models.song_credit_entry import SongCreditEntry  # noqa: E402
from app.models.song_media_asset import (  # noqa: E402
    SONG_MEDIA_KIND_COVER_ART,
    SONG_MEDIA_KIND_MASTER_AUDIO,
    SongMediaAsset,
)
from app.models.song_artist_split import SongArtistSplit  # noqa: E402
from app.models.subgenre import Subgenre  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.user_balance import UserBalance  # noqa: E402
from app.seeding.seed_common import ensure_schema, reset_existing_data  # noqa: E402
from app.services.payout_service import (  # noqa: E402
    ensure_treasury_entities,
    get_treasury_artist,
)
from app.services.payout_v2_snapshot_engine import generate_payout_lines  # noqa: E402
from app.services.snapshot_service import build_snapshot  # noqa: E402
from app.services.stream_service import StreamService  # noqa: E402
from app.services.user_service import (  # noqa: E402
    SEED_LISTENER_PLACEHOLDER_PASSWORD,
    create_user,
)
from app.workers.listen_worker import process_listening_event  # noqa: E402

# Shared Algorand-format wallet for local/dev only. In production, each artist must use a unique wallet.
ADMIN_WALLET = "APQVRSIZTCOOHLVLFOTZAEFPO3VNA5DHXBQNGUQARQP2EBWWLDMKUMNKIA"

# Product-facing payouts are Algorand USDC. The DB column must be ``crypto`` (or ``wallet``): ``settlement_worker``
# only recognizes those values for on-chain settlement. Do not store ``algorand`` here or artists will be skipped.
PAYOUT_METHOD_STORED = "crypto"

CORE_BATCH_ANTIFRAUD = "policy:core_seed_v1"
MASTER_REL = "uploads/songs/seed_master.wav"
COVER_REL = "uploads/covers/seed_cover.png"
LISTEN_DURATION_SEC = 120
MOOD_ROTATION = (
    ("energetic", "focus"),
    ("melancholic", "late night"),
    ("uplifting", "workout"),
    ("chill", "ambient"),
    ("dreamy", "cinematic"),
)
CITIES = (
    ("US", "Brooklyn"),
    ("GB", "London"),
    ("DE", "Berlin"),
    ("FR", "Paris"),
    ("JP", "Tokyo"),
    ("CA", "Montreal"),
    ("BR", "São Paulo"),
    ("AU", "Melbourne"),
    ("ES", "Barcelona"),
    ("NL", "Amsterdam"),
)


def _run_seed_genres_main() -> None:
    """Reuse ``scripts/seed_genres.py`` entrypoint (no separate CLI step)."""
    path = BACKEND_ROOT / "scripts" / "seed_genres.py"
    spec = importlib.util.spec_from_file_location("seed_genres", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load seed_genres from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.main()


def _ensure_core_users(db: Session) -> tuple[list[User], dict[str, int]]:
    """Upsert users by email user01@test.com … user10@test.com."""
    created = 0
    updated = 0
    users: list[User] = []
    by_email: dict[str, int] = {}
    for i in range(1, 11):
        email = f"user{i:02d}@test.com"
        row = db.query(User).filter(User.email == email).first()
        display = f"Core User {i:02d}"
        if row is None:
            row = create_user(
                db,
                email,
                SEED_LISTENER_PLACEHOLDER_PASSWORD,
                display,
                username=None,
            )
            created += 1
        else:
            prof = getattr(row, "profile", None)
            if prof is not None and prof.display_name != display:
                prof.display_name = display
                updated += 1
        users.append(row)
        by_email[email] = int(row.id)
    db.commit()
    for u in users:
        db.refresh(u)
    return users, {"created": created, "updated": updated}


def _ensure_core_artists(db: Session, users: list[User]) -> tuple[list[Artist], dict[str, int]]:
    """Upsert artists by system_key artist_01 … artist_10; one per user."""
    if len(users) != 10:
        raise RuntimeError("Expected 10 users")
    created = 0
    updated = 0
    artists: list[Artist] = []
    for idx, user in enumerate(users, start=1):
        sk = f"artist_{idx:02d}"
        row = db.query(Artist).filter(Artist.system_key == sk).first()
        name = f"Core Artist {idx:02d}"  # display only; matching is by system_key
        if row is None:
            row = Artist(
                name=name,
                system_key=sk,
                user_id=int(user.id),
                payout_method=PAYOUT_METHOD_STORED,
                payout_wallet_address=ADMIN_WALLET,
                is_system=False,
            )
            db.add(row)
            db.flush()
            created += 1
        else:
            dirty = False
            if row.name != name:
                row.name = name
                dirty = True
            if int(row.user_id or 0) != int(user.id):
                row.user_id = int(user.id)
                dirty = True
            if (row.payout_method or "").strip().lower() != PAYOUT_METHOD_STORED:
                row.payout_method = PAYOUT_METHOD_STORED
                dirty = True
            if (row.payout_wallet_address or "").strip() != ADMIN_WALLET:
                row.payout_wallet_address = ADMIN_WALLET
                dirty = True
            if dirty:
                updated += 1
        artists.append(row)
    db.commit()
    for a in artists:
        db.refresh(a)
    return artists, {"created": created, "updated": updated}


def _resolve_genre_subgenre_ids(db: Session) -> tuple[int, int]:
    g = db.query(Genre).filter(Genre.slug == "electronic").one()
    sg = (
        db.query(Subgenre)
        .filter(Subgenre.genre_id == int(g.id), Subgenre.name == "House")
        .one()
    )
    return int(g.id), int(sg.id)


def _ensure_core_songs(
    db: Session,
    artists: list[Artist],
    genre_id: int,
    subgenre_id: int,
) -> tuple[list[Song], dict[str, int]]:
    """Upsert 50 songs by system_key artist_XX_song_YY."""
    created = 0
    updated = 0
    songs: list[Song] = []
    for a in artists:
        prefix = (a.system_key or "").strip()
        if not prefix.startswith("artist_"):
            raise RuntimeError(f"Unexpected artist system_key: {a.system_key!r}")
        for sn in range(1, 6):
            sk = f"{prefix}_song_{sn:02d}"
            title = f"{prefix.replace('_', ' ').title()} — piece {sn}"
            moods = list(MOOD_ROTATION[(int(a.id) + sn) % len(MOOD_ROTATION)])
            cc, city = CITIES[(int(a.id) + sn) % len(CITIES)]
            row = db.query(Song).filter(Song.system_key == sk).one_or_none()
            if row is None:
                row = Song(
                    title=title,
                    system_key=sk,
                    artist_id=int(a.id),
                    is_system=False,
                    genre_id=genre_id,
                    subgenre_id=subgenre_id,
                    moods=moods,
                    country_code=cc,
                    city=city,
                    duration_seconds=180,
                    file_path=MASTER_REL,
                    upload_status="ready",
                    state=SONG_STATE_READY_FOR_RELEASE,
                )
                db.add(row)
                db.flush()
                created += 1
            else:
                dirty = False
                if row.title != title:
                    row.title = title
                    dirty = True
                if int(row.artist_id or 0) != int(a.id):
                    row.artist_id = int(a.id)
                    dirty = True
                if int(row.genre_id or 0) != genre_id:
                    row.genre_id = genre_id
                    dirty = True
                if int(row.subgenre_id or 0) != subgenre_id:
                    row.subgenre_id = subgenre_id
                    dirty = True
                if (row.moods or []) != moods:
                    row.moods = moods
                    dirty = True
                if (row.country_code or "") != cc:
                    row.country_code = cc
                    dirty = True
                if (row.city or "") != city:
                    row.city = city
                    dirty = True
                if int(row.duration_seconds or 0) != 180:
                    row.duration_seconds = 180
                    dirty = True
                if (row.file_path or "") != MASTER_REL:
                    row.file_path = MASTER_REL
                    dirty = True
                if (row.upload_status or "") != "ready":
                    row.upload_status = "ready"
                    dirty = True
                cur_state = getattr(row.state, "value", row.state)
                if str(cur_state or "") != str(SONG_STATE_READY_FOR_RELEASE):
                    row.state = SONG_STATE_READY_FOR_RELEASE
                    dirty = True
                if row.deleted_at is not None:
                    row.deleted_at = None
                    dirty = True
                if dirty:
                    updated += 1
            songs.append(row)
    db.commit()
    for s in songs:
        db.refresh(s)
    return songs, {"created": created, "updated": updated}


def _ensure_song_credits(db: Session, song: Song, artist: Artist) -> None:
    primary = (artist.name or "Artist").strip() or "Artist"
    existing = (
        db.query(SongCreditEntry)
        .filter(SongCreditEntry.song_id == int(song.id))
        .order_by(SongCreditEntry.position.asc())
        .all()
    )
    want = [
        (1, primary, "songwriter"),
        (2, "Core Seed Producer", "producer"),
    ]
    by_pos = {int(r.position): r for r in existing}
    for pos, disp, role in want:
        r = by_pos.get(pos)
        if r is None:
            db.add(
                SongCreditEntry(
                    song_id=int(song.id),
                    position=pos,
                    display_name=disp,
                    role=role,
                )
            )
        else:
            r.display_name = disp
            r.role = role


def _ensure_song_splits(db: Session, song: Song) -> None:
    aid = int(song.artist_id)
    row = (
        db.query(SongArtistSplit)
        .filter(
            SongArtistSplit.song_id == int(song.id),
            SongArtistSplit.artist_id == aid,
        )
        .first()
    )
    if row is None:
        db.add(
            SongArtistSplit(
                song_id=int(song.id),
                artist_id=aid,
                share=1.0,
                split_bps=10000,
            )
        )
    else:
        row.share = 1.0
        row.split_bps = 10000


def _ensure_song_media(db: Session, song: Song) -> None:
    sid = int(song.id)
    for kind, path, mime in (
        (SONG_MEDIA_KIND_MASTER_AUDIO, MASTER_REL, "audio/wav"),
        (SONG_MEDIA_KIND_COVER_ART, COVER_REL, "image/png"),
    ):
        sha = hashlib.sha256(f"{sid}:{kind}:{path}".encode()).hexdigest()
        asset = (
            db.query(SongMediaAsset)
            .filter(SongMediaAsset.song_id == sid, SongMediaAsset.kind == kind)
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


def _ensure_credits_splits_media(db: Session, songs: list[Song], artists: list[Artist]) -> None:
    by_id = {int(a.id): a for a in artists}
    for s in songs:
        art = by_id.get(int(s.artist_id))
        if art is None:
            raise RuntimeError(f"No artist for song {s.system_key}")
        _ensure_song_credits(db, s, art)
        _ensure_song_splits(db, s)
        _ensure_song_media(db, s)
    db.commit()


def _ensure_user_balances(db: Session, users: list[User]) -> None:
    for u in users:
        bal = db.query(UserBalance).filter(UserBalance.user_id == int(u.id)).first()
        if bal is None:
            db.add(UserBalance(user_id=int(u.id), monthly_amount=50.0))
        else:
            bal.monthly_amount = 50.0
    db.commit()


def _song_listen_weights(songs: list[Song]) -> list[float]:
    """Strong front-loaded weights (non-uniform across 50 songs)."""
    w: list[float] = []
    for idx in range(len(songs)):
        if idx < 3:
            w.append(120.0)
        elif idx < 8:
            w.append(40.0)
        elif idx < 15:
            w.append(12.0)
        else:
            w.append(1.0)
    return w


def _simulate_listening_nonuniform(
    users: list[User],
    songs: list[Song],
    *,
    rng: random.Random,
) -> tuple[int, int]:
    """
    Users 1–9 generate listens; user 10 has balance only (treasury fallback in payout).

    Deterministic idempotency keys: ``seed_core_listen:{user_id}:{song_id}`` at most once
    per (user, song) so re-runs do not duplicate rows.
    """
    service = StreamService()
    supports_event_timestamp = "event_timestamp" in inspect.signature(
        service.process_stream
    ).parameters

    listeners = users[:9]
    weights = _song_listen_weights(songs)
    target_events = 220
    seen_pairs: set[tuple[int, int]] = set()
    inserted = 0
    duplicates = 0
    failed = 0

    base_ts = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=14)
    slot = 0
    max_attempts = target_events * 80
    attempts = 0

    while len(seen_pairs) < target_events and attempts < max_attempts:
        attempts += 1
        song = rng.choices(songs, weights=weights, k=1)[0]
        user = rng.choice(listeners)
        uid = int(user.id)
        sid = int(song.id)
        if (uid, sid) in seen_pairs:
            continue
        seen_pairs.add((uid, sid))
        ikey = f"seed_core_listen:{uid}:{sid}"
        ts = base_ts + timedelta(minutes=45 * slot)
        slot += 1
        db_i = SessionLocal()
        try:
            kwargs = {
                "db": db_i,
                "user_id": uid,
                "song_id": sid,
                "duration": LISTEN_DURATION_SEC,
                "idempotency_key": ikey,
            }
            if supports_event_timestamp:
                kwargs["event_timestamp"] = ts
            out = service.process_stream(**kwargs)
            st = out.get("status")
            if st == "duplicate":
                duplicates += 1
                continue
            if st not in ("ok",):
                failed += 1
                continue
            eid = out.get("event_id")
            if not eid:
                failed += 1
                continue
            inserted += 1
            process_listening_event(int(eid))
        except Exception:
            failed += 1
        finally:
            db_i.close()

    if len(seen_pairs) < target_events:
        raise RuntimeError(
            f"Could not place {target_events} distinct (user,song) listens "
            f"(got {len(seen_pairs)}); try lowering target_events or increasing users."
        )

    return inserted, duplicates + failed


def _ledger_already_finalized(db: Session) -> bool:
    return (
        db.query(PayoutBatch.id)
        .filter(
            PayoutBatch.antifraud_version == CORE_BATCH_ANTIFRAUD,
            PayoutBatch.status.in_(("finalized", "posted")),
        )
        .first()
        is not None
    )


def _build_ledger(db: Session, policy_id: str) -> tuple[int, int]:
    min_ts = db.query(func.min(ListeningEvent.timestamp)).scalar()
    max_ts = db.query(func.max(ListeningEvent.timestamp)).scalar()
    if min_ts is None or max_ts is None:
        raise RuntimeError("No listening events; cannot build payout batch")

    period_start = min_ts - timedelta(seconds=1)
    period_end = max_ts + timedelta(seconds=1)

    batch = PayoutBatch(
        period_start_at=period_start,
        period_end_at=period_end,
        status="draft",
        currency="USD",
        calculation_version="v2",
        antifraud_version=CORE_BATCH_ANTIFRAUD,
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    batch_id = int(batch.id)

    build_snapshot(
        batch_id=batch_id,
        period_start_at=period_start,
        period_end_at=period_end,
        policy_id=policy_id,
    )
    n_lines = int(
        generate_payout_lines(
            batch_id,
            auto_run_settlement=False,
            auto_settlement_async=False,
        )
    )
    return batch_id, n_lines


def _validate_ledger(db: Session, treasury_artist_id: int) -> None:
    n_lines = int(db.query(func.count(PayoutLine.id)).scalar() or 0)
    if n_lines < 1:
        raise RuntimeError("Validation failed: no payout_line rows")

    royalty_artists = (
        db.query(PayoutLine.artist_id)
        .filter(
            PayoutLine.line_type == "royalty",
            PayoutLine.artist_id.isnot(None),
            PayoutLine.artist_id != treasury_artist_id,
        )
        .distinct()
        .all()
    )
    ra_count = len({int(r[0]) for r in royalty_artists if r[0] is not None})
    if ra_count < 2:
        raise RuntimeError(
            f"Validation failed: expected payout_lines for >=2 non-treasury artists, got {ra_count}"
        )

    treasury_cents = (
        db.query(func.coalesce(func.sum(PayoutLine.amount_cents), 0))
        .filter(PayoutLine.line_type == "treasury")
        .scalar()
    )
    if int(treasury_cents or 0) < 1:
        raise RuntimeError("Validation failed: treasury must receive a positive share (line_type=treasury)")


def _print_summary(
    *,
    users: dict[str, int],
    artists: dict[str, int],
    songs: dict[str, int],
    listens: int,
    batch_id: int,
    payout_lines_inserted_run: int | None = None,
) -> None:
    db = SessionLocal()
    try:
        total_paid = int(
            db.query(func.coalesce(func.sum(PayoutLine.amount_cents), 0)).scalar() or 0
        )
        n_lines = int(db.query(func.count(PayoutLine.id)).scalar() or 0)
    finally:
        db.close()

    print("\n=== seed_core_state summary ===")
    print(f"users_created={users['created']} users_updated={users['updated']}")
    print(f"artists_created={artists['created']} artists_updated={artists['updated']}")
    print(f"songs_created={songs['created']} songs_updated={songs['updated']}")
    print(f"listening_events_inserted={listens}")
    print(f"payout_batch_id={batch_id}")
    print(f"payout_lines_total={n_lines}")
    print(f"payout_total_cents_distributed={total_paid}")
    if payout_lines_inserted_run is not None:
        print(f"payout_lines_inserted_this_run={payout_lines_inserted_run}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Canonical core state seed (idempotent by default).")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Wipe domain tables via reset_existing_data() before seeding.",
    )
    parser.add_argument(
        "--policy-id",
        type=str,
        default="v1",
        help="Economics policy id for build_snapshot (default: v1).",
    )
    parser.add_argument(
        "--rng-seed",
        type=int,
        default=42,
        help="Deterministic RNG seed for listening simulation placement.",
    )
    args = parser.parse_args()

    ensure_schema()
    if args.reset:
        reset_existing_data()

    db = SessionLocal()
    try:
        ensure_treasury_entities(db)
        db.commit()
    finally:
        db.close()

    _run_seed_genres_main()

    uc: dict[str, int] = {}
    ac: dict[str, int] = {}
    sc: dict[str, int] = {}

    db = SessionLocal()
    try:
        users, uc = _ensure_core_users(db)
        artists, ac = _ensure_core_artists(db, users)
        gid, sgid = _resolve_genre_subgenre_ids(db)
        songs, sc = _ensure_core_songs(db, artists, gid, sgid)
        _ensure_credits_splits_media(db, songs, artists)
        _ensure_user_balances(db, users)

        tr = get_treasury_artist(db)
        if tr is None:
            raise RuntimeError("Treasury artist missing after ensure_treasury_entities")
        treasury_id = int(tr.id)

        if _ledger_already_finalized(db):
            print(
                "\n=== seed_core_state: ledger already finalized for this seed tag; "
                "skipping listening simulation and payout batch ==="
            )
            _validate_ledger(db, treasury_id)
            core_listens = int(
                db.query(func.count(ListeningEvent.id))
                .filter(ListeningEvent.idempotency_key.like("seed_core_listen:%"))
                .scalar()
                or 0
            )
            last_batch = (
                db.query(PayoutBatch)
                .filter(
                    PayoutBatch.antifraud_version == CORE_BATCH_ANTIFRAUD,
                    PayoutBatch.status.in_(("finalized", "posted")),
                )
                .order_by(PayoutBatch.id.desc())
                .first()
            )
            bid = int(last_batch.id) if last_batch is not None else 0
            _print_summary(
                users=uc,
                artists=ac,
                songs=sc,
                listens=core_listens,
                batch_id=bid,
                payout_lines_inserted_run=None,
            )
            return

        rng = random.Random(int(args.rng_seed))
        listens, _noise = _simulate_listening_nonuniform(users, songs, rng=rng)
    finally:
        db.close()

    db = SessionLocal()
    try:
        tr = get_treasury_artist(db)
        if tr is None:
            raise RuntimeError("Treasury artist missing")
        treasury_id = int(tr.id)
        batch_id, n_lines = _build_ledger(db, policy_id=args.policy_id)
        _validate_ledger(db, treasury_id)
    finally:
        db.close()

    db = SessionLocal()
    try:
        core_listens = int(
            db.query(func.count(ListeningEvent.id))
            .filter(ListeningEvent.idempotency_key.like("seed_core_listen:%"))
            .scalar()
            or 0
        )
    finally:
        db.close()

    _print_summary(
        users=uc,
        artists=ac,
        songs=sc,
        listens=core_listens,
        batch_id=batch_id,
        payout_lines_inserted_run=n_lines,
    )


if __name__ == "__main__":
    main()
