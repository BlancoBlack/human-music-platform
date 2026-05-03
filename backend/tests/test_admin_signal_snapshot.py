"""Admin signal snapshot aggregates (read-only)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.artist import Artist
from app.models.discovery_event import DiscoveryEvent
from app.models.like_event import LikeEvent
from app.models.playlist import Playlist, PlaylistTrack
from app.models.playlist_reorder_event import PlaylistReorderEvent
from app.models.song import SONG_STATE_DRAFT, Song
from app.models.user import User
from app.services.admin_signal_snapshot import build_admin_signal_snapshot
from app.services.like_service import LIKED_SONGS_PLAYLIST_TITLE


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    db = TestSession()
    try:
        u = User(email="adm@test.example", username="adm_u")
        db.add(u)
        db.flush()
        a = Artist(slug="adm-art", name="A", owner_user_id=u.id)
        db.add(a)
        db.flush()
        s1 = Song(
            slug="adm-s1",
            title="T1",
            artist_id=a.id,
            upload_status="ready",
            state=SONG_STATE_DRAFT,
        )
        db.add(s1)
        db.flush()
        pl = Playlist(
            owner_user_id=u.id,
            title="Pub",
            is_public=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(pl)
        db.flush()
        db.add(PlaylistTrack(playlist_id=int(pl.id), song_id=int(s1.id), position=1))
        db.commit()
        yield db
    finally:
        db.close()


def test_build_admin_signal_snapshot_empty_tables_ok(db_session: Session) -> None:
    snap = build_admin_signal_snapshot(db_session)
    assert snap["reorder"]["overview"]["row_count"] == 0
    assert snap["reorder"]["scale"]["avg_weighted_sum"] == 0.0
    assert snap["reorder"]["scale"]["p95_weighted_sum"] == 0.0
    assert snap["likes"]["overview"]["total_events"] == 0
    assert snap["top_reorder_coverage_in_discovery"] == 0.0
    assert snap["likes_reorder_overlap"] == 0.0


def test_build_admin_signal_snapshot_reorder_and_coverage(db_session: Session) -> None:
    uid = int(db_session.query(User.id).scalar())
    pid = int(db_session.query(Playlist.id).scalar())
    s1 = int(db_session.query(Song.id).scalar())
    now = datetime.utcnow()
    pu = datetime.now(timezone.utc)
    db_session.add(
        PlaylistReorderEvent(
            user_id=uid,
            playlist_id=pid,
            song_id=s1,
            old_position=2,
            new_position=1,
            delta_position=1,
            playlist_updated_at=pu,
            created_at=now,
        )
    )
    db_session.add(
        DiscoveryEvent(
            event_type="impression",
            request_id="r1",
            user_id=uid,
            song_id=s1,
            artist_id=None,
            section="for_you",
            position=0,
            metadata_json={},
        )
    )
    db_session.commit()

    snap = build_admin_signal_snapshot(db_session)
    assert snap["reorder"]["overview"]["row_count"] == 1
    assert snap["reorder"]["scale"]["avg_weighted_sum"] == pytest.approx(1.0)
    assert snap["reorder"]["scale"]["p95_weighted_sum"] == pytest.approx(1.0)
    assert snap["reorder"]["top_reorder_songs"][0]["song_id"] == s1
    assert snap["reorder"]["top_reorder_songs"][0]["weighted_sum"] == 1.0
    assert snap["reorder"]["top_reorder_songs"][0]["title"] == "T1"
    assert snap["reorder"]["top_reorder_songs"][0]["artist_name"] == "A"
    assert snap["top_reorder_coverage_in_discovery"] == 1.0


def test_build_admin_signal_snapshot_likes(db_session: Session) -> None:
    uid = int(db_session.query(User.id).scalar())
    s1 = int(db_session.query(Song.id).scalar())
    mature_ts = datetime.utcnow() - timedelta(hours=1)
    db_session.add(LikeEvent(user_id=uid, song_id=s1, created_at=mature_ts))
    db_session.commit()
    snap = build_admin_signal_snapshot(db_session)
    assert snap["likes"]["overview"]["total_events"] == 1
    assert snap["likes"]["top_liked_songs"][0]["song_id"] == s1
    assert snap["likes"]["top_liked_songs"][0]["count"] == 1
    assert snap["likes"]["top_liked_songs"][0]["title"] == "T1"
    assert snap["likes"]["top_liked_songs"][0]["artist_name"] == "A"
    assert snap["likes"]["top_liked_songs"][0].get("artist") == "A"
    assert "ranking_context" in snap["likes"]
    assert snap["likes"]["ranking_context"]["sample_songs"] >= 1


def test_coverage_uses_distinct_songs_not_rows(db_session: Session) -> None:
    uid = int(db_session.query(User.id).scalar())
    pid = int(db_session.query(Playlist.id).scalar())
    s1 = int(db_session.query(Song.id).scalar())
    now = datetime.utcnow()
    pu = datetime.now(timezone.utc)
    db_session.add(
        PlaylistReorderEvent(
            user_id=uid,
            playlist_id=pid,
            song_id=s1,
            old_position=2,
            new_position=1,
            delta_position=1,
            playlist_updated_at=pu,
            created_at=now,
        )
    )
    for rid in ("r1", "r2", "r3"):
        db_session.add(
            DiscoveryEvent(
                event_type="impression",
                request_id=rid,
                user_id=uid,
                song_id=s1,
                artist_id=None,
                section="for_you",
                position=0,
                metadata_json={},
            )
        )
    db_session.commit()
    snap = build_admin_signal_snapshot(db_session)
    assert snap["top_reorder_coverage_in_discovery"] == 1.0


def test_likes_reorder_overlap(db_session: Session) -> None:
    uid = int(db_session.query(User.id).scalar())
    pid = int(db_session.query(Playlist.id).scalar())
    s1 = int(db_session.query(Song.id).scalar())
    now = datetime.utcnow()
    pu = datetime.now(timezone.utc)
    db_session.add(
        PlaylistReorderEvent(
            user_id=uid,
            playlist_id=pid,
            song_id=s1,
            old_position=2,
            new_position=1,
            delta_position=1,
            playlist_updated_at=pu,
            created_at=now,
        )
    )
    db_session.add(
        LikeEvent(user_id=uid, song_id=s1, created_at=now - timedelta(hours=1))
    )
    db_session.commit()
    snap = build_admin_signal_snapshot(db_session)
    assert snap["likes_reorder_overlap"] == pytest.approx(1.0)


def test_liked_playlist_reduces_share(db_session: Session) -> None:
    uid = int(db_session.query(User.id).scalar())
    s1 = int(db_session.query(Song.id).scalar())
    now = datetime.utcnow()
    pu = datetime.now(timezone.utc)
    liked_pl = Playlist(
        owner_user_id=uid,
        title=LIKED_SONGS_PLAYLIST_TITLE,
        is_public=False,
        created_at=now,
        updated_at=now,
    )
    db_session.add(liked_pl)
    db_session.flush()
    lid = int(liked_pl.id)
    db_session.add(PlaylistTrack(playlist_id=lid, song_id=s1, position=1))
    db_session.add(
        PlaylistReorderEvent(
            user_id=uid,
            playlist_id=lid,
            song_id=s1,
            old_position=2,
            new_position=1,
            delta_position=1,
            playlist_updated_at=pu,
            created_at=now,
        )
    )
    db_session.commit()
    snap = build_admin_signal_snapshot(db_session)
    assert snap["reorder"]["liked_share_of_weighted_sum"] == pytest.approx(1.0)
