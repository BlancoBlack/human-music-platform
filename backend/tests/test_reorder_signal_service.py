"""Runtime reorder signal aggregation for discovery."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.artist import Artist
from app.models.playlist import Playlist, PlaylistTrack
from app.models.playlist_reorder_event import PlaylistReorderEvent
from app.models.song import SONG_STATE_DRAFT, Song
from app.models.user import User
from app.services.like_service import LIKED_SONGS_PLAYLIST_TITLE
from app.services.reorder_signal_service import load_reorder_signal_by_song


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
        u = User(email="rs@test.example", username="rs_user")
        db.add(u)
        db.flush()
        a = Artist(slug="rs-artist", name="RS", owner_user_id=u.id)
        db.add(a)
        db.flush()
        s1 = Song(
            slug="rs-s1",
            title="A",
            artist_id=a.id,
            upload_status="ready",
            state=SONG_STATE_DRAFT,
        )
        s2 = Song(
            slug="rs-s2",
            title="B",
            artist_id=a.id,
            upload_status="ready",
            state=SONG_STATE_DRAFT,
        )
        db.add_all([s1, s2])
        db.flush()
        pl = Playlist(
            owner_user_id=u.id,
            title="Mix",
            is_public=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(pl)
        db.flush()
        db.add_all(
            [
                PlaylistTrack(playlist_id=int(pl.id), song_id=int(s1.id), position=1),
                PlaylistTrack(playlist_id=int(pl.id), song_id=int(s2.id), position=2),
            ]
        )
        db.commit()
        yield db
    finally:
        db.close()


def test_load_reorder_signal_anonymous_empty(db_session: Session) -> None:
    s1 = int(db_session.query(Song.id).filter_by(slug="rs-s1").scalar())
    assert load_reorder_signal_by_song(db_session, None, [s1]) == {}


def test_load_reorder_signal_positive_sum_per_event_clamp(db_session: Session) -> None:
    """LEAST(delta,5): 9→5 and 1→1 → sum 6 → log1p(6)."""
    uid = int(db_session.query(User.id).scalar())
    pid = int(db_session.query(Playlist.id).scalar())
    s1 = int(db_session.query(Song.id).filter_by(slug="rs-s1").scalar())
    now = datetime.utcnow()
    pu = datetime.now(timezone.utc)

    db_session.add(
        PlaylistReorderEvent(
            user_id=uid,
            playlist_id=pid,
            song_id=s1,
            old_position=10,
            new_position=1,
            delta_position=9,
            playlist_updated_at=pu,
            created_at=now,
        )
    )
    db_session.add(
        PlaylistReorderEvent(
            user_id=uid,
            playlist_id=pid,
            song_id=s1,
            old_position=5,
            new_position=4,
            delta_position=1,
            playlist_updated_at=pu,
            created_at=now,
        )
    )
    db_session.commit()

    out = load_reorder_signal_by_song(db_session, uid, [s1])
    assert out[s1] == pytest.approx(math.log1p(6.0))


def test_load_reorder_signal_ignores_non_positive_delta(db_session: Session) -> None:
    uid = int(db_session.query(User.id).scalar())
    pid = int(db_session.query(Playlist.id).scalar())
    s1 = int(db_session.query(Song.id).filter_by(slug="rs-s1").scalar())
    now = datetime.utcnow()
    pu = datetime.now(timezone.utc)
    db_session.add(
        PlaylistReorderEvent(
            user_id=uid,
            playlist_id=pid,
            song_id=s1,
            old_position=1,
            new_position=3,
            delta_position=-2,
            playlist_updated_at=pu,
            created_at=now,
        )
    )
    db_session.commit()
    assert load_reorder_signal_by_song(db_session, uid, [s1]) == {}


def test_load_reorder_signal_caps_sum_at_20(db_session: Session) -> None:
    uid = int(db_session.query(User.id).scalar())
    pid = int(db_session.query(Playlist.id).scalar())
    s1 = int(db_session.query(Song.id).filter_by(slug="rs-s1").scalar())
    now = datetime.utcnow()
    pu = datetime.now(timezone.utc)
    for _ in range(5):
        db_session.add(
            PlaylistReorderEvent(
                user_id=uid,
                playlist_id=pid,
                song_id=s1,
                old_position=20,
                new_position=10,
                delta_position=10,
                playlist_updated_at=pu,
                created_at=now,
            )
        )
    db_session.commit()
    out = load_reorder_signal_by_song(db_session, uid, [s1])
    assert out[s1] == pytest.approx(math.log1p(20.0))


def test_load_reorder_signal_respects_window(db_session: Session) -> None:
    uid = int(db_session.query(User.id).scalar())
    pid = int(db_session.query(Playlist.id).scalar())
    s1 = int(db_session.query(Song.id).filter_by(slug="rs-s1").scalar())
    pu = datetime.now(timezone.utc)
    old = datetime.utcnow() - timedelta(days=40)
    db_session.add(
        PlaylistReorderEvent(
            user_id=uid,
            playlist_id=pid,
            song_id=s1,
            old_position=3,
            new_position=1,
            delta_position=2,
            playlist_updated_at=pu,
            created_at=old,
        )
    )
    db_session.commit()
    assert load_reorder_signal_by_song(db_session, uid, [s1]) == {}


def test_load_reorder_signal_14_day_window(db_session: Session) -> None:
    uid = int(db_session.query(User.id).scalar())
    pid = int(db_session.query(Playlist.id).scalar())
    s1 = int(db_session.query(Song.id).filter_by(slug="rs-s1").scalar())
    pu = datetime.now(timezone.utc)
    outside = datetime.utcnow() - timedelta(days=15)
    db_session.add(
        PlaylistReorderEvent(
            user_id=uid,
            playlist_id=pid,
            song_id=s1,
            old_position=2,
            new_position=1,
            delta_position=1,
            playlist_updated_at=pu,
            created_at=outside,
        )
    )
    db_session.commit()
    assert load_reorder_signal_by_song(db_session, uid, [s1]) == {}


def test_liked_playlist_downweight(db_session: Session) -> None:
    uid = int(db_session.query(User.id).scalar())
    pu = datetime.now(timezone.utc)
    now = datetime.utcnow()

    liked_pl = Playlist(
        owner_user_id=uid,
        title=LIKED_SONGS_PLAYLIST_TITLE,
        is_public=False,
        created_at=now,
        updated_at=now,
    )
    db_session.add(liked_pl)
    db_session.flush()
    liked_pid = int(liked_pl.id)
    s1 = int(db_session.query(Song.id).filter_by(slug="rs-s1").scalar())
    db_session.add(
        PlaylistTrack(playlist_id=liked_pid, song_id=s1, position=1),
    )
    db_session.add(
        PlaylistReorderEvent(
            user_id=uid,
            playlist_id=liked_pid,
            song_id=s1,
            old_position=3,
            new_position=1,
            delta_position=2,
            playlist_updated_at=pu,
            created_at=now,
        )
    )
    db_session.commit()

    out = load_reorder_signal_by_song(db_session, uid, [s1])
    # LEAST(2,5)*0.4 = 0.8
    assert out[s1] == pytest.approx(math.log1p(0.8))


def test_public_same_title_not_downweighted(db_session: Session) -> None:
    """Title match alone is insufficient — must be private (liked canonical)."""
    uid = int(db_session.query(User.id).scalar())
    pu = datetime.now(timezone.utc)
    now = datetime.utcnow()
    pub_liked_title = Playlist(
        owner_user_id=uid,
        title=LIKED_SONGS_PLAYLIST_TITLE,
        is_public=True,
        created_at=now,
        updated_at=now,
    )
    db_session.add(pub_liked_title)
    db_session.flush()
    ppid = int(pub_liked_title.id)
    s1 = int(db_session.query(Song.id).filter_by(slug="rs-s1").scalar())
    db_session.add(PlaylistTrack(playlist_id=ppid, song_id=s1, position=1))
    db_session.add(
        PlaylistReorderEvent(
            user_id=uid,
            playlist_id=ppid,
            song_id=s1,
            old_position=2,
            new_position=1,
            delta_position=1,
            playlist_updated_at=pu,
            created_at=now,
        )
    )
    db_session.commit()
    out = load_reorder_signal_by_song(db_session, uid, [s1])
    assert out[s1] == pytest.approx(math.log1p(1.0))


def test_debug_env_logs_top_playlist(caplog, db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HM_DEBUG_REORDER_SIGNAL", "1")
    caplog.set_level(logging.INFO)

    uid = int(db_session.query(User.id).scalar())
    pid = int(db_session.query(Playlist.id).scalar())
    s1 = int(db_session.query(Song.id).filter_by(slug="rs-s1").scalar())
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
    db_session.commit()

    load_reorder_signal_by_song(db_session, uid, [s1])
    assert any("reorder_signal_debug" in r.message for r in caplog.records)
    assert any(str(pid) in r.message for r in caplog.records)
