"""Playlist MVP service-layer rules."""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.artist import Artist
from app.models.release import (
    RELEASE_APPROVAL_STATUS_DRAFT,
    RELEASE_STATE_DRAFT,
    RELEASE_TYPE_SINGLE,
    Release,
)
from app.models.release_media_asset import (
    RELEASE_MEDIA_ASSET_TYPE_COVER_ART,
    ReleaseMediaAsset,
)
from app.models.song import SONG_STATE_DRAFT, Song
from app.models.song_media_asset import SONG_MEDIA_KIND_MASTER_AUDIO, SongMediaAsset
from app.models.playlist import Playlist
from app.models.playlist_reorder_event import PlaylistReorderEvent
from app.models.user import User
from app.services.media_urls import public_media_url_from_stored_path
from app.services.media_utils import effective_song_cover
from app.services.playlist_service import (
    PlaylistForbiddenError,
    PlaylistValidationError,
    add_track_to_playlist,
    create_playlist,
    get_playlist,
    get_playlist_for_playback,
    playlist_to_detail,
    playlist_to_detail_enriched,
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


def test_playlist_to_detail_enriched_empty(db_session: Session) -> None:
    uid = int(db_session.query(User.id).filter(User.email == "pl.owner@test.example").scalar())
    pl = create_playlist(
        db_session,
        user_id=uid,
        title="E",
        description=None,
        is_public=True,
    )
    db_session.commit()
    db_session.refresh(pl)
    loaded = get_playlist(db_session, playlist_id=int(pl.id), viewer_user_id=uid)
    d = playlist_to_detail_enriched(db_session, loaded)
    assert d["cover_urls"] == []
    assert d["tracks"] == []


def test_playlist_to_detail_enriched_track_metadata(db_session: Session) -> None:
    uid = int(db_session.query(User.id).filter(User.email == "pl.owner@test.example").scalar())
    artist = db_session.query(Artist).filter(Artist.slug == "pl-artist").one()
    s1 = db_session.query(Song).filter(Song.slug == "pl-song-1").one()

    rel = Release(
        slug="pl-release-cover",
        title="With Cover",
        artist_id=int(artist.id),
        owner_user_id=uid,
        type=RELEASE_TYPE_SINGLE,
        release_date=datetime.utcnow(),
        state=RELEASE_STATE_DRAFT,
        approval_status=RELEASE_APPROVAL_STATUS_DRAFT,
    )
    db_session.add(rel)
    db_session.flush()
    s1.release_id = int(rel.id)
    db_session.add(
        ReleaseMediaAsset(
            release_id=int(rel.id),
            asset_type=RELEASE_MEDIA_ASSET_TYPE_COVER_ART,
            file_path="uploads/releases/pl_cov.jpg",
        )
    )
    db_session.add(
        SongMediaAsset(
            song_id=int(s1.id),
            kind=SONG_MEDIA_KIND_MASTER_AUDIO,
            file_path="uploads/songs/pl_master.mp3",
            mime_type="audio/mpeg",
            byte_size=100,
            sha256="a" * 64,
        )
    )
    db_session.commit()

    pl = create_playlist(db_session, user_id=uid, title="Mix", description=None, is_public=False)
    db_session.flush()
    pid = int(pl.id)
    add_track_to_playlist(db_session, playlist_id=pid, song_id=int(s1.id), owner_user_id=uid)
    db_session.commit()

    loaded = get_playlist(db_session, playlist_id=pid, viewer_user_id=uid)
    d = playlist_to_detail_enriched(db_session, loaded)
    assert len(d["tracks"]) == 1
    tr = d["tracks"][0]
    assert tr["song_id"] == int(s1.id)
    assert tr["position"] == 1
    assert tr["title"] == "One"
    assert tr["artist_name"] == "PL Artist"
    assert tr["cover_url"] == "/uploads/releases/pl_cov.jpg"
    assert tr["cover_url"] == public_media_url_from_stored_path(
        effective_song_cover(db_session, s1)
    )
    assert tr["audio_url"] == "/uploads/songs/pl_master.mp3"
    assert d["cover_urls"] == ["/uploads/releases/pl_cov.jpg"]


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


def test_reorder_creates_playlist_reorder_events(db_session: Session) -> None:
    uid = int(db_session.query(User.id).filter(User.email == "pl.owner@test.example").scalar())
    s1 = int(db_session.query(Song.id).filter(Song.slug == "pl-song-1").scalar())
    s2 = int(db_session.query(Song.id).filter(Song.slug == "pl-song-2").scalar())
    pl = create_playlist(
        db_session, user_id=uid, title="Signals", description=None, is_public=True
    )
    db_session.flush()
    pid = int(pl.id)
    add_track_to_playlist(db_session, playlist_id=pid, song_id=s1, owner_user_id=uid)
    add_track_to_playlist(db_session, playlist_id=pid, song_id=s2, owner_user_id=uid)
    db_session.commit()

    reorder_playlist_tracks(
        db_session,
        playlist_id=pid,
        ordered_song_ids=[s2, s1],
        owner_user_id=uid,
    )
    db_session.commit()

    rows = (
        db_session.query(PlaylistReorderEvent)
        .filter(PlaylistReorderEvent.playlist_id == pid)
        .order_by(PlaylistReorderEvent.song_id.asc())
        .all()
    )
    assert len(rows) == 2
    by_song = {r.song_id: r for r in rows}
    assert by_song[s1].old_position == 1
    assert by_song[s1].new_position == 2
    assert by_song[s1].delta_position == -1
    assert by_song[s2].old_position == 2
    assert by_song[s2].new_position == 1
    assert by_song[s2].delta_position == 1
    assert int(by_song[s1].user_id) == uid

    pl_row = db_session.query(Playlist).filter(Playlist.id == pid).one()
    pl_u = pl_row.updated_at
    for r in rows:
        pu = r.playlist_updated_at
        assert pu is not None
        pu_naive = pu.replace(tzinfo=None) if pu.tzinfo else pu
        assert pu_naive == pl_u


def test_noop_reorder_creates_no_playlist_reorder_events(db_session: Session) -> None:
    uid = int(db_session.query(User.id).filter(User.email == "pl.owner@test.example").scalar())
    s1 = int(db_session.query(Song.id).filter(Song.slug == "pl-song-1").scalar())
    s2 = int(db_session.query(Song.id).filter(Song.slug == "pl-song-2").scalar())
    pl = create_playlist(db_session, user_id=uid, title="Noop", description=None, is_public=True)
    db_session.flush()
    pid = int(pl.id)
    add_track_to_playlist(db_session, playlist_id=pid, song_id=s1, owner_user_id=uid)
    add_track_to_playlist(db_session, playlist_id=pid, song_id=s2, owner_user_id=uid)
    db_session.commit()

    reorder_playlist_tracks(
        db_session,
        playlist_id=pid,
        ordered_song_ids=[s1, s2],
        owner_user_id=uid,
    )
    db_session.commit()

    n = db_session.query(PlaylistReorderEvent).filter_by(playlist_id=pid).count()
    assert n == 0


def test_reorder_delta_position_three_tracks(db_session: Session) -> None:
    uid = int(db_session.query(User.id).filter(User.email == "pl.owner@test.example").scalar())
    artist = db_session.query(Artist).filter(Artist.slug == "pl-artist").one()
    s1 = int(db_session.query(Song.id).filter(Song.slug == "pl-song-1").scalar())
    s2 = int(db_session.query(Song.id).filter(Song.slug == "pl-song-2").scalar())
    s3 = Song(
        slug="pl-song-3",
        title="Three",
        artist_id=int(artist.id),
        upload_status="ready",
        state=SONG_STATE_DRAFT,
    )
    db_session.add(s3)
    db_session.flush()
    s3_id = int(s3.id)

    pl = create_playlist(db_session, user_id=uid, title="ThreeTr", description=None, is_public=True)
    db_session.flush()
    pid = int(pl.id)
    add_track_to_playlist(db_session, playlist_id=pid, song_id=s1, owner_user_id=uid)
    add_track_to_playlist(db_session, playlist_id=pid, song_id=s2, owner_user_id=uid)
    add_track_to_playlist(db_session, playlist_id=pid, song_id=s3_id, owner_user_id=uid)
    db_session.commit()

    # [1,2,3] -> [3,1,2]
    reorder_playlist_tracks(
        db_session,
        playlist_id=pid,
        ordered_song_ids=[s3_id, s1, s2],
        owner_user_id=uid,
    )
    db_session.commit()

    rows = {r.song_id: r for r in db_session.query(PlaylistReorderEvent).filter_by(playlist_id=pid)}
    assert rows[s1].delta_position == rows[s1].old_position - rows[s1].new_position == -1
    assert rows[s2].delta_position == -1
    assert rows[s3_id].delta_position == 2


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
