"""User likes: persisted events + sync to private ``Liked Songs`` playlist."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.like_event import LikeEvent
from app.models.playlist import Playlist, PlaylistTrack
from app.models.song import Song
from app.services.playlist_service import (
    PlaylistValidationError,
    add_track_to_playlist,
    create_playlist,
    remove_track_from_playlist,
)

LIKED_SONGS_PLAYLIST_TITLE = "Liked Songs"


class LikeValidationError(Exception):
    """Invalid like/unlike input (e.g. missing song)."""


def _ensure_song_exists(db: Session, song_id: int) -> None:
    row = (
        db.query(Song.id)
        .filter(Song.id == int(song_id), Song.deleted_at.is_(None))
        .first()
    )
    if row is None:
        raise LikeValidationError("Song not found")


def get_or_create_liked_songs_playlist(db: Session, *, user_id: int) -> Playlist:
    """
    Private playlist titled ``LIKED_SONGS_PLAYLIST_TITLE`` owned by ``user_id``.

    Matches only non-deleted, **private** playlists with that exact title so a user's
    public playlist with the same name does not hijack the system playlist.
    """
    uid = int(user_id)
    pl = (
        db.query(Playlist)
        .filter(
            Playlist.owner_user_id == uid,
            Playlist.title == LIKED_SONGS_PLAYLIST_TITLE,
            Playlist.is_public.is_(False),
            Playlist.deleted_at.is_(None),
        )
        .order_by(Playlist.id.asc())
        .first()
    )
    if pl is not None:
        return pl
    return create_playlist(
        db,
        user_id=uid,
        title=LIKED_SONGS_PLAYLIST_TITLE,
        description=None,
        is_public=False,
    )


def _playlist_track_exists(db: Session, *, playlist_id: int, song_id: int) -> bool:
    row = (
        db.query(PlaylistTrack.id)
        .filter(
            PlaylistTrack.playlist_id == int(playlist_id),
            PlaylistTrack.song_id == int(song_id),
        )
        .first()
    )
    return row is not None


def like_song(db: Session, *, user_id: int, song_id: int) -> dict:
    """
    Idempotent: ensures ``LikeEvent`` row and playlist track for ``Liked Songs``.

    Raises ``LikeValidationError`` if the song does not exist or is soft-deleted.
    """
    uid = int(user_id)
    sid = int(song_id)
    _ensure_song_exists(db, sid)

    existing = (
        db.query(LikeEvent.id)
        .filter(LikeEvent.user_id == uid, LikeEvent.song_id == sid)
        .first()
    )
    if existing is None:
        try:
            with db.begin_nested():
                db.add(
                    LikeEvent(
                        user_id=uid,
                        song_id=sid,
                        created_at=datetime.utcnow(),
                    )
                )
                db.flush()
        except IntegrityError:
            pass

    pl = get_or_create_liked_songs_playlist(db, user_id=uid)
    pid = int(pl.id)
    if not _playlist_track_exists(db, playlist_id=pid, song_id=sid):
        add_track_to_playlist(
            db,
            playlist_id=pid,
            song_id=sid,
            owner_user_id=uid,
        )

    return {"song_id": sid, "liked": True}


def unlike_song(db: Session, *, user_id: int, song_id: int) -> dict:
    """Idempotent: removes like row and track from ``Liked Songs`` when present."""
    uid = int(user_id)
    sid = int(song_id)

    db.query(LikeEvent).filter(LikeEvent.user_id == uid, LikeEvent.song_id == sid).delete(
        synchronize_session=False
    )

    pl = (
        db.query(Playlist)
        .filter(
            Playlist.owner_user_id == uid,
            Playlist.title == LIKED_SONGS_PLAYLIST_TITLE,
            Playlist.is_public.is_(False),
            Playlist.deleted_at.is_(None),
        )
        .order_by(Playlist.id.asc())
        .first()
    )
    if pl is not None:
        try:
            remove_track_from_playlist(
                db,
                playlist_id=int(pl.id),
                song_id=sid,
                owner_user_id=uid,
            )
        except PlaylistValidationError:
            pass

    return {"song_id": sid, "liked": False}
