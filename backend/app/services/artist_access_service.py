from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.artist import Artist
from app.models.song import Song
from app.models.user import User
from app.services.rbac_service import has_permission


def create_artist_for_user(
    db: Session,
    *,
    current_user: User,
    name: str,
    **artist_fields,
) -> Artist:
    artist_name = (name or "").strip()
    if not artist_name:
        raise ValueError("Artist name is required")
    artist = Artist(
        name=artist_name,
        owner_user_id=int(current_user.id),
        **artist_fields,
    )
    db.add(artist)
    return artist


def get_user_owned_artists(user_id: int, db: Session) -> list[Artist]:
    return (
        db.query(Artist)
        .filter(Artist.owner_user_id == int(user_id))
        .order_by(Artist.id.asc())
        .all()
    )


def can_edit_artist(user: User, artist: Artist, db: Session | None = None) -> bool:
    if has_permission(user, "admin_full_access", db=db):
        return True
    if has_permission(user, "edit_any_artist", db=db):
        return True
    if has_permission(user, "edit_own_artist", db=db) and int(artist.owner_user_id or 0) == int(
        user.id
    ):
        return True
    return False


def can_upload_song(user: User, artist: Artist, db: Session) -> bool:
    if bool(user.onboarding_completed):
        return True
    existing_count = (
        db.query(Song.id)
        .filter(Song.artist_id == int(artist.id), Song.deleted_at.is_(None))
        .count()
    )
    return int(existing_count) < 1
