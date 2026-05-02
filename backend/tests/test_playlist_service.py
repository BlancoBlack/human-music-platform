"""Playlist MVP service-layer rules."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.artist import Artist
from app.models.song import SONG_STATE_DRAFT, Song
from app.models.user import User
from app.services.playlist_service import (
    PlaylistForbiddenError,
    PlaylistValidationError,
    add_track_to_playlist,
    create_playlist,
    get_playlist,
    get_playlist_for_playback,
    playlist_to_detail,
    remove_track_from_playlist,
    reorder_playlist_tracks,
)


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
        u1 = User(email="pl.owner@test.example", username="pl_owner")
        u2 = User(email="pl.other@test.example", username="pl_other")
        db.add_all([u1, u2])
        db.flush()
        a = Artist(slug="pl-artist", name="PL Artist", owner_user_id=u1.id)
        db.add(a)
        db.flush()
        s1 = Song(
            slug="pl-song-1",
            title="One",
            artist_id=a.id,
            upload_status="ready",
            state=SONG_STATE_DRAFT,
        )
        s2 = Song(
            slug="pl-song-2",
            title="Two",
            artist_id=a.id,
            upload_status="ready",
            state=SONG_STATE_DRAFT,
        )
        db.add_all([s1, s2])
        db.commit()
        yield db
    finally:
        db.close()


def test_create_and_get_playlist(db_session: Session) -> None:
    uid = int(db_session.query(User.id).filter(User.email == "pl.owner@test.example").scalar())
    pl = create_playlist(
        db_session,
        user_id=uid,
        title="  My Mix  ",
        description="  ",
        is_public=False,
    )
    db_session.commit()
    db_session.refresh(pl)
    loaded = get_playlist(db_session, playlist_id=int(pl.id), viewer_user_id=uid)
    d = playlist_to_detail(loaded)
    assert d["title"] == "My Mix"
    assert d["description"] is None
    assert d["is_public"] is False
    assert d["tracks"] == []


def test_add_remove_reorder(db_session: Session) -> None:
    uid = int(db_session.query(User.id).filter(User.email == "pl.owner@test.example").scalar())
    s1 = int(db_session.query(Song.id).filter(Song.slug == "pl-song-1").scalar())
    s2 = int(db_session.query(Song.id).filter(Song.slug == "pl-song-2").scalar())
    pl = create_playlist(
        db_session, user_id=uid, title="R", description=None, is_public=True
    )
    db_session.flush()
    pid = int(pl.id)
    add_track_to_playlist(db_session, playlist_id=pid, song_id=s1, owner_user_id=uid)
    add_track_to_playlist(db_session, playlist_id=pid, song_id=s2, owner_user_id=uid)
    db_session.commit()
    g = playlist_to_detail(get_playlist(db_session, playlist_id=pid, viewer_user_id=uid))
    assert [t["song_id"] for t in g["tracks"]] == [s1, s2]
    reorder_playlist_tracks(
        db_session,
        playlist_id=pid,
        ordered_song_ids=[s2, s1],
        owner_user_id=uid,
    )
    db_session.commit()
    g = playlist_to_detail(get_playlist(db_session, playlist_id=pid, viewer_user_id=uid))
    assert [t["song_id"] for t in g["tracks"]] == [s2, s1]
    remove_track_from_playlist(
        db_session, playlist_id=pid, song_id=s2, owner_user_id=uid
    )
    db_session.commit()
    g = playlist_to_detail(get_playlist(db_session, playlist_id=pid, viewer_user_id=uid))
    assert [t["song_id"] for t in g["tracks"]] == [s1]


def test_duplicate_track_rejected(db_session: Session) -> None:
    uid = int(db_session.query(User.id).filter(User.email == "pl.owner@test.example").scalar())
    s1 = int(db_session.query(Song.id).filter(Song.slug == "pl-song-1").scalar())
    pl = create_playlist(
        db_session, user_id=uid, title="D", description=None, is_public=False
    )
    db_session.flush()
    pid = int(pl.id)
    add_track_to_playlist(db_session, playlist_id=pid, song_id=s1, owner_user_id=uid)
    db_session.flush()
    with pytest.raises(PlaylistValidationError):
        add_track_to_playlist(db_session, playlist_id=pid, song_id=s1, owner_user_id=uid)


def test_non_owner_cannot_mutate(db_session: Session) -> None:
    uid = int(db_session.query(User.id).filter(User.email == "pl.owner@test.example").scalar())
    other = int(db_session.query(User.id).filter(User.email == "pl.other@test.example").scalar())
    s1 = int(db_session.query(Song.id).filter(Song.slug == "pl-song-1").scalar())
    pl = create_playlist(
        db_session, user_id=uid, title="X", description=None, is_public=False
    )
    db_session.flush()
    pid = int(pl.id)
    with pytest.raises(PlaylistForbiddenError):
        add_track_to_playlist(db_session, playlist_id=pid, song_id=s1, owner_user_id=other)


def test_private_playlist_hidden_from_non_owner(db_session: Session) -> None:
    uid = int(db_session.query(User.id).filter(User.email == "pl.owner@test.example").scalar())
    other = int(db_session.query(User.id).filter(User.email == "pl.other@test.example").scalar())
    pl = create_playlist(
        db_session, user_id=uid, title="Private", description=None, is_public=False
    )
    db_session.commit()
    pid = int(pl.id)
    with pytest.raises(PlaylistForbiddenError):
        get_playlist(db_session, playlist_id=pid, viewer_user_id=other)


def test_playback_public_anonymous_ok(db_session: Session) -> None:
    uid = int(db_session.query(User.id).filter(User.email == "pl.owner@test.example").scalar())
    s1 = int(db_session.query(Song.id).filter(Song.slug == "pl-song-1").scalar())
    s2 = int(db_session.query(Song.id).filter(Song.slug == "pl-song-2").scalar())
    pl = create_playlist(
        db_session, user_id=uid, title="Pub", description=None, is_public=True
    )
    db_session.flush()
    pid = int(pl.id)
    add_track_to_playlist(db_session, playlist_id=pid, song_id=s1, owner_user_id=uid)
    add_track_to_playlist(db_session, playlist_id=pid, song_id=s2, owner_user_id=uid)
    reorder_playlist_tracks(
        db_session,
        playlist_id=pid,
        ordered_song_ids=[s2, s1],
        owner_user_id=uid,
    )
    db_session.commit()
    body = get_playlist_for_playback(db_session, playlist_id=pid, user_id=None)
    assert body["playlist"]["id"] == pid
    assert body["playlist"]["is_public"] is True
    assert body["playlist"]["owner_user_id"] == uid
    assert [t["song_id"] for t in body["tracks"]] == [s2, s1]
    assert body["tracks"][0]["position"] == 1


def test_playback_private_requires_owner(db_session: Session) -> None:
    uid = int(db_session.query(User.id).filter(User.email == "pl.owner@test.example").scalar())
    other = int(db_session.query(User.id).filter(User.email == "pl.other@test.example").scalar())
    pl = create_playlist(
        db_session, user_id=uid, title="Priv", description=None, is_public=False
    )
    db_session.commit()
    pid = int(pl.id)
    with pytest.raises(PlaylistForbiddenError):
        get_playlist_for_playback(db_session, playlist_id=pid, user_id=None)
    with pytest.raises(PlaylistForbiddenError):
        get_playlist_for_playback(db_session, playlist_id=pid, user_id=other)
    body = get_playlist_for_playback(db_session, playlist_id=pid, user_id=uid)
    assert body["playlist"]["id"] == pid
    assert body["tracks"] == []
