"""Curated discovery rail from public playlists (finalize step — daily seeded shuffle)."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.artist import Artist
from app.models.playlist import Playlist, PlaylistTrack
from app.models.song import SONG_STATE_DRAFT, Song
from app.models.song_media_asset import SONG_MEDIA_KIND_MASTER_AUDIO, SongMediaAsset
from app.models.user import User
from app.services.discovery_ranking import (
    build_curated_ids_from_public_playlists,
    finalize_discovery_ranking,
)


def _playable_song(slug_suffix: int, *, artist_id: int, ts: datetime) -> tuple[Song, SongMediaAsset]:
    slug = f"cur-pl-{slug_suffix}"
    song = Song(
        slug=slug,
        title=f"C{slug_suffix}",
        artist_id=artist_id,
        upload_status="ready",
        state=SONG_STATE_DRAFT,
        created_at=ts,
    )
    asset = SongMediaAsset(
        song_id=None,
        kind=SONG_MEDIA_KIND_MASTER_AUDIO,
        file_path=f"/x/{slug}.wav",
        mime_type="audio/wav",
        byte_size=10,
        sha256="b" * 64,
    )
    return song, asset


def _song_id(db: Session, suffix: int) -> int:
    return int(db.query(Song.id).filter(Song.slug == f"cur-pl-{suffix}").scalar())


@pytest.fixture()
def curated_db() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    db = TestSession()
    try:
        ts = datetime(2025, 6, 1)
        u = User(email="cur-pl@test.example", username="cur_pl")
        db.add(u)
        db.flush()
        a = Artist(slug="cur-pl-artist", name="CurPL", owner_user_id=u.id)
        db.add(a)
        db.flush()
        pairs: list[tuple[Song, SongMediaAsset]] = []
        for i in range(1, 8):
            pairs.append(_playable_song(i, artist_id=a.id, ts=ts))
        for song, _ in pairs:
            db.add(song)
        db.flush()
        for song, asset in pairs:
            asset.song_id = song.id
            db.add(asset)
        # p2 newer updated_at → processed first (DESC). Three positions; query limits to 2.
        p2 = Playlist(
            owner_user_id=u.id,
            title="P_newer",
            is_public=True,
            created_at=ts,
            updated_at=datetime(2025, 6, 3),
        )
        p1 = Playlist(
            owner_user_id=u.id,
            title="P_older",
            is_public=True,
            created_at=ts,
            updated_at=datetime(2025, 6, 2),
        )
        db.add_all([p2, p1])
        db.flush()
        db.add_all(
            [
                PlaylistTrack(playlist_id=int(p2.id), song_id=_song_id(db, 1), position=1),
                PlaylistTrack(playlist_id=int(p2.id), song_id=_song_id(db, 2), position=2),
                PlaylistTrack(playlist_id=int(p2.id), song_id=_song_id(db, 3), position=3),
                PlaylistTrack(playlist_id=int(p1.id), song_id=_song_id(db, 4), position=1),
                PlaylistTrack(playlist_id=int(p1.id), song_id=_song_id(db, 5), position=2),
            ]
        )
        db.commit()
        yield db
    finally:
        db.close()


def test_curated_empty_when_no_playlists(curated_db: Session) -> None:
    curated_db.query(PlaylistTrack).delete(synchronize_session=False)
    curated_db.query(Playlist).delete(synchronize_session=False)
    curated_db.commit()
    out = build_curated_ids_from_public_playlists(curated_db, [1, 2, 3], utc_date=date(2026, 1, 1))
    assert out == []


def test_curated_stable_same_utc_day(curated_db: Session) -> None:
    all_ids = [int(r[0]) for r in curated_db.query(Song.id).order_by(Song.id.asc()).all()]
    d = date(2030, 3, 15)
    a = build_curated_ids_from_public_playlists(curated_db, all_ids, utc_date=d)
    b = build_curated_ids_from_public_playlists(curated_db, all_ids, utc_date=d)
    assert a == b
    assert len(set(a)) == len(a)


def test_curated_changes_across_utc_days(curated_db: Session) -> None:
    all_ids = [int(r[0]) for r in curated_db.query(Song.id).order_by(Song.id.asc()).all()]
    base = date(2030, 1, 1)
    orders: list[list[int]] = []
    for i in range(40):
        orders.append(
            build_curated_ids_from_public_playlists(
                curated_db, all_ids, utc_date=base + timedelta(days=i)
            )
        )
    assert all(sorted(o) == sorted(orders[0]) for o in orders)
    assert len(set(tuple(o) for o in orders)) >= 2


def test_curated_third_track_not_included_per_playlist(curated_db: Session) -> None:
    sid3 = _song_id(curated_db, 3)
    all_ids = [int(r[0]) for r in curated_db.query(Song.id).order_by(Song.id.asc()).all()]
    base = date(2028, 1, 1)
    for i in range(60):
        out = build_curated_ids_from_public_playlists(
            curated_db, all_ids, utc_date=base + timedelta(days=i)
        )
        assert sid3 not in out


def test_curated_no_playlist_contributes_more_than_two_tracks(curated_db: Session) -> None:
    """SQL limit(2) per playlist: newest playlist's position-3 track never appears."""
    all_ids = [int(r[0]) for r in curated_db.query(Song.id).order_by(Song.id.asc()).all()]
    p_newer = curated_db.query(Playlist).filter(Playlist.title == "P_newer").one()
    rows = (
        curated_db.query(PlaylistTrack.song_id)
        .filter(PlaylistTrack.playlist_id == int(p_newer.id))
        .order_by(PlaylistTrack.position.asc())
        .limit(2)
        .all()
    )
    newer_two = {int(r[0]) for r in rows}
    out = build_curated_ids_from_public_playlists(curated_db, all_ids, utc_date=date(2020, 1, 1))
    assert set(out).issubset(all_ids)
    assert len(set(out) & newer_two) <= 2
    assert len(out) <= 8


def test_finalize_explicit_curated_ids_filters_by_candidates(curated_db: Session) -> None:
    """Explicit curated_ids branch does not require ids to exist in DB playlists."""
    scored = [{"song_id": 1, "score": 1.0, "for_you_score": 1.0, "rel": 0.0, "pop_raw": 0.0, "pop_log": 0.0}]
    final = finalize_discovery_ranking(
        scored,
        [1, 2],
        {1: 1},
        db=curated_db,
        curated_ids=[99],
    )
    assert final["curated_ids"] == []


def test_finalize_explicit_curated_ids_keeps_order_when_in_candidates(curated_db: Session) -> None:
    one = _song_id(curated_db, 1)
    two = _song_id(curated_db, 2)
    scored = [
        {"song_id": one, "score": 1.0, "for_you_score": 1.0, "rel": 0.0, "pop_raw": 0.0, "pop_log": 0.0},
        {"song_id": two, "score": 0.9, "for_you_score": 0.9, "rel": 0.0, "pop_raw": 0.0, "pop_log": 0.0},
    ]
    final = finalize_discovery_ranking(
        scored,
        [one, two],
        {one: 1, two: 1},
        db=curated_db,
        curated_ids=[two, one],
    )
    assert final["curated_ids"] == [two, one]


def test_finalize_with_db_builds_curated(curated_db: Session) -> None:
    all_ids = [int(r[0]) for r in curated_db.query(Song.id).order_by(Song.id.asc()).all()]
    scored = [
        {
            "song_id": sid,
            "score": 1.0,
            "for_you_score": 1.0,
            "rel": 0.0,
            "pop_raw": 0.0,
            "pop_log": 0.0,
        }
        for sid in all_ids
    ]
    artist_by = {sid: 1 for sid in all_ids}
    d = date(2019, 7, 7)
    a = finalize_discovery_ranking(scored, all_ids, artist_by, db=curated_db, curated_utc_date=d)
    b = finalize_discovery_ranking(scored, all_ids, artist_by, db=curated_db, curated_utc_date=d)
    assert a["curated_ids"] == b["curated_ids"]
    assert len(a["curated_ids"]) >= 1
