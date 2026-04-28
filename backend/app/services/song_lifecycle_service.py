"""Soft delete and ownership checks for artist-owned songs."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.artist import Artist
from app.models.song import Song
from app.models.user import User
from app.services.artist_access_service import get_artist_owner_id


class SongNotFoundError(Exception):
    """Song does not exist in the active product-facing catalog."""


class SongOwnershipError(Exception):
    """Caller does not own the song or song is protected."""


def assert_user_owns_song(db: Session, user: User, song_id: int) -> Song:
    song = (
        db.query(Song)
        .filter(Song.id == int(song_id), Song.deleted_at.is_(None))
        .first()
    )
    if song is None:
        raise SongNotFoundError("Song not found.")
    if bool(getattr(song, "is_system", False)):
        raise SongOwnershipError("This song cannot be modified.")
    artist = db.query(Artist).filter(Artist.id == int(song.artist_id)).first()
    if artist is None:
        raise SongOwnershipError("Artist not found for this song.")
    owner_id = get_artist_owner_id(artist)
    if owner_id is None or int(owner_id) != int(user.id):
        raise SongOwnershipError("You can only modify songs you own.")
    return song


def delete_owned_song(db: Session, user: User, song_id: int) -> None:
    """
    Soft-delete a song from product-facing surfaces.
    """
    song = assert_user_owns_song(db, user, song_id)
    song.deleted_at = datetime.utcnow()
    db.add(song)
    db.commit()
