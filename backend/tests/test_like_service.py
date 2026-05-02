"""Like events + ``Liked Songs`` playlist sync."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.artist import Artist
from app.models.like_event import LikeEvent
from app.models.playlist import Playlist, PlaylistTrack
from app.models.song import SONG_STATE_DRAFT, Song
from app.models.user import User
from app.services.like_service import LIKED_SONGS_PLAYLIST_TITLE, LikeValidationError, like_song, unlike_song


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
        u = User(email="like.owner@test.example", username="like_owner")
        db.add(u)
        db.flush()
        a = Artist(slug="like-artist", name="LA", owner_user_id=u.id)
        db.add(a)
        db.flush()
        s = Song(
            slug="like-song",
            title="L",
            artist_id=a.id,
            upload_status="ready",
            state=SONG_STATE_DRAFT,
        )
        db.add(s)
        db.commit()
        yield db
    finally:
        db.close()


def test_like_idempotent_and_playlist_sync(db_session: Session) -> None:
    uid = int(db_session.query(User.id).scalar())
    sid = int(db_session.query(Song.id).scalar())

    like_song(db_session, user_id=uid, song_id=sid)
    db_session.commit()

    like_song(db_session, user_id=uid, song_id=sid)
    db_session.commit()

    assert db_session.query(LikeEvent).filter_by(user_id=uid, song_id=sid).count() == 1
    pl = (
        db_session.query(Playlist)
        .filter_by(owner_user_id=uid, title=LIKED_SONGS_PLAYLIST_TITLE)
        .one()
    )
    assert pl.title == LIKED_SONGS_PLAYLIST_TITLE
    assert pl.is_public is False
    assert db_session.query(PlaylistTrack).filter_by(playlist_id=pl.id, song_id=sid).count() == 1


def test_unlike_removes_event_and_track(db_session: Session) -> None:
    uid = int(db_session.query(User.id).scalar())
    sid = int(db_session.query(Song.id).scalar())
    like_song(db_session, user_id=uid, song_id=sid)
    db_session.commit()
    pl_id = int(
        db_session.query(Playlist.id)
        .filter_by(owner_user_id=uid, title=LIKED_SONGS_PLAYLIST_TITLE)
        .scalar()
    )

    unlike_song(db_session, user_id=uid, song_id=sid)
    db_session.commit()

    assert db_session.query(LikeEvent).filter_by(user_id=uid, song_id=sid).count() == 0
    assert db_session.query(PlaylistTrack).filter_by(playlist_id=pl_id, song_id=sid).count() == 0


def test_unlike_never_liked_no_crash(db_session: Session) -> None:
    uid = int(db_session.query(User.id).scalar())
    sid = int(db_session.query(Song.id).scalar())
    unlike_song(db_session, user_id=uid, song_id=sid)
    db_session.commit()


def test_like_unknown_song(db_session: Session) -> None:
    uid = int(db_session.query(User.id).scalar())
    with pytest.raises(LikeValidationError):
        like_song(db_session, user_id=uid, song_id=999_999)
