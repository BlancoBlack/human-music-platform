from __future__ import annotations

import importlib.util
from pathlib import Path

from sqlalchemy import func

from app.core.database import SessionLocal
from app.models.artist import Artist
from app.models.payout_batch import PayoutBatch
from app.models.payout_line import PayoutLine
from app.models.release import RELEASE_TYPE_ALBUM, RELEASE_TYPE_EP, RELEASE_TYPE_SINGLE, Release
from app.models.song import Song
from app.models.user import User
from app.models.user_balance import UserBalance
from app.models.listening_event import ListeningEvent
from app.seeding.seed_common import ensure_schema, reset_existing_data
from app.seeding.seed_system.artists import upsert_seed_artists
from app.seeding.seed_system.core import (
    ARTIST_NAMES,
    CORE_BATCH_ANTIFRAUD,
    COVER_REL_PATH,
    MASTER_REL_PATH,
    SEED_SCALES,
    USER_PROFILES,
    WALLET_ADDRESS,
    release_date_for_slot,
    release_state,
    song_state,
)
from app.seeding.seed_system.listening import simulate_listening
from app.seeding.seed_system.media import ensure_song_credits_splits_and_media
from app.seeding.seed_system.payouts import build_snapshot_and_payouts, validate_payouts
from app.seeding.seed_system.releases import ReleaseTemplate, upsert_artist_releases
from app.seeding.seed_system.songs import resolve_seed_genre_ids, upsert_artist_songs
from app.seeding.seed_system.users import upsert_seed_users
from app.services.payout_service import ensure_treasury_entities


def run_seed_system(*, reset: bool, scale: str, rng_seed: int = 42, policy_id: str = "v1") -> dict[str, object]:
    if scale not in SEED_SCALES:
        raise ValueError(f"Unsupported scale={scale!r}; choose one of {', '.join(SEED_SCALES)}")
    ensure_schema()
    if reset:
        reset_existing_data()
    _seed_genres()

    db = SessionLocal()
    try:
        ensure_treasury_entities(db)
        db.commit()

        users = upsert_seed_users(db, USER_PROFILES)
        artists = upsert_seed_artists(db, users=users, artist_names=ARTIST_NAMES, wallet_address=WALLET_ADDRESS)
        genre_id, subgenre_id = resolve_seed_genre_ids(db)
        all_songs: list[Song] = []

        for idx, artist in enumerate(artists, start=1):
            releases = upsert_artist_releases(
                db,
                artist=artist,
                templates=[
                    ReleaseTemplate("album", "Album", RELEASE_TYPE_ALBUM, release_date_for_slot(idx, 0), release_state()),
                    ReleaseTemplate("ep", "EP", RELEASE_TYPE_EP, release_date_for_slot(idx, 1), release_state()),
                    ReleaseTemplate("single", "Single", RELEASE_TYPE_SINGLE, release_date_for_slot(idx, 2), release_state()),
                ],
            )
            artist_songs = upsert_artist_songs(
                db,
                artist=artist,
                artist_idx=idx,
                releases=releases,
                genre_id=genre_id,
                subgenre_id=subgenre_id,
                song_state=song_state(),
                file_path=MASTER_REL_PATH,
            )
            all_songs.extend(artist_songs)

        ensure_song_credits_splits_and_media(
            db,
            songs=all_songs,
            artists_by_id={int(a.id): a for a in artists},
            master_path=MASTER_REL_PATH,
            cover_path=COVER_REL_PATH,
        )
        _set_user_balances(db, users)
        _validate_slugs(db)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    db = SessionLocal()
    try:
        users_for_listening = db.query(User).filter(User.email.like("%@seed.hmp.local")).order_by(User.id.asc()).all()
        songs_for_listening = (
            db.query(Song)
            .filter(Song.system_key.like("seed.song.%"), Song.deleted_at.is_(None))
            .order_by(Song.id.asc())
            .all()
        )
    finally:
        db.close()

    listen_stats = simulate_listening(
        users=users_for_listening,
        songs=songs_for_listening,
        rng_seed=rng_seed,
        listens_per_user_min=SEED_SCALES[scale].listens_per_user_min,
        listens_per_user_max=SEED_SCALES[scale].listens_per_user_max,
        max_repeat_per_user_song=SEED_SCALES[scale].max_repeat_per_user_song,
    )

    db = SessionLocal()
    try:
        batch_id, inserted_lines = build_snapshot_and_payouts(
            db,
            antifraud_version=CORE_BATCH_ANTIFRAUD,
            policy_id=policy_id,
        )
        validate_payouts(db, batch_id=batch_id)
        _assert_final_seed_contract(db, batch_id=batch_id)
        db.commit()
        return _summary(db, batch_id=batch_id, inserted_lines=inserted_lines, listen_stats=listen_stats, scale=scale)
    finally:
        db.close()


def _seed_genres() -> None:
    backend_root = Path(__file__).resolve().parents[3]
    path = backend_root / "scripts" / "seed_genres.py"
    spec = importlib.util.spec_from_file_location("seed_genres", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load seed_genres from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.main()


def _set_user_balances(db, users) -> None:
    for user in users:
        row = db.query(UserBalance).filter(UserBalance.user_id == int(user.id)).one_or_none()
        if row is None:
            db.add(UserBalance(user_id=int(user.id), monthly_amount=50.0))
        else:
            row.monthly_amount = 50.0
    db.flush()


def _validate_slugs(db) -> None:
    _assert_non_empty_slugs(db, Artist, "artist")
    _assert_non_empty_slugs(db, Release, "release")
    _assert_non_empty_slugs(db, Song, "song")
    _assert_unique_slugs(db, Artist, "artist")
    _assert_unique_slugs(db, Release, "release")
    _assert_unique_slugs(db, Song, "song")
    _assert_collision_happened(db)


def _assert_non_empty_slugs(db, model, label: str) -> None:
    missing = int(db.query(func.count(model.id)).filter((model.slug.is_(None)) | (model.slug == "")).scalar() or 0)
    if missing > 0:
        raise RuntimeError(f"Slug validation failed: {missing} {label} rows missing slug.")


def _assert_unique_slugs(db, model, label: str) -> None:
    duplicate = (
        db.query(model.slug)
        .group_by(model.slug)
        .having(func.count(model.id) > 1)
        .first()
    )
    if duplicate is not None:
        raise RuntimeError(f"Slug validation failed: duplicate {label} slug found: {duplicate[0]}")


def _assert_collision_happened(db) -> None:
    slugs = [str(row[0]) for row in db.query(Song.slug).filter(Song.slug.like("midnight-pulse%")).all()]
    if "midnight-pulse" not in slugs or "midnight-pulse-2" not in slugs:
        raise RuntimeError("Slug collision validation failed: expected midnight-pulse + midnight-pulse-2.")


def _summary(db, *, batch_id: int, inserted_lines: int, listen_stats: dict[str, object], scale: str) -> dict[str, object]:
    return {
        "scale": scale,
        "users": int(db.query(func.count(User.id)).filter(User.email.like("%@seed.hmp.local")).scalar() or 0),
        "artists": int(
            db.query(func.count(Artist.id))
            .filter(Artist.is_system.is_(False), Artist.system_key.like("seed.artist.%"))
            .scalar()
            or 0
        ),
        "releases": int(
            db.query(func.count(Release.id))
            .filter(Release.artist_id.in_(db.query(Artist.id).filter(Artist.system_key.like("seed.artist.%"))))
            .scalar()
            or 0
        ),
        "songs": int(
            db.query(func.count(Song.id))
            .filter(Song.is_system.is_(False), Song.system_key.like("seed.song.%"))
            .scalar()
            or 0
        ),
        "listen_inserted": int(listen_stats.get("inserted", 0)),
        "listen_failed": int(listen_stats.get("failed", 0)),
        "listen_duplicates": int(listen_stats.get("duplicates", 0)),
        "worker_failures": int(listen_stats.get("worker_failures", 0)),
        "payout_batch_id": batch_id,
        "payout_lines_inserted": inserted_lines,
        "latest_batch_status": db.query(PayoutBatch.status).filter(PayoutBatch.id == batch_id).scalar(),
    }


def _assert_final_seed_contract(db, *, batch_id: int) -> None:
    artists_count = int(
        db.query(func.count(Artist.id))
        .filter(Artist.is_system.is_(False), Artist.system_key.like("seed.artist.%"))
        .scalar()
        or 0
    )
    releases_count = int(
        db.query(func.count(Release.id))
        .filter(Release.artist_id.in_(db.query(Artist.id).filter(Artist.system_key.like("seed.artist.%"))))
        .scalar()
        or 0
    )
    songs_count = int(
        db.query(func.count(Song.id))
        .filter(Song.is_system.is_(False), Song.system_key.like("seed.song.%"))
        .scalar()
        or 0
    )
    listens_count = int(
        db.query(func.count(ListeningEvent.id))
        .filter(ListeningEvent.idempotency_key.like("seed_system_listen:%"))
        .scalar()
        or 0
    )
    payout_lines_count = int(
        db.query(func.count(PayoutLine.id))
        .filter(PayoutLine.batch_id == int(batch_id))
        .scalar()
        or 0
    )

    if artists_count < 1:
        raise RuntimeError("Seed contract failed: no seeded artists were created.")
    if releases_count < 1:
        raise RuntimeError("Seed contract failed: no seeded releases were created.")
    if songs_count < 1:
        raise RuntimeError("Seed contract failed: no seeded songs were created.")
    if listens_count < 1:
        raise RuntimeError("Seed contract failed: no seeded listening events were created.")
    if payout_lines_count < 1:
        raise RuntimeError("Seed contract failed: no payout_lines were generated.")
