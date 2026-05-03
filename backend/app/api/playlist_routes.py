"""Playlist CRUD (MVP) + optional-auth playback read."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_optional_user
from app.core.database import get_db
from app.models.user import User
from app.services.playlist_service import (
    PlaylistForbiddenError,
    PlaylistNotFoundError,
    PlaylistValidationError,
    add_track_to_playlist,
    create_playlist,
    get_playlist,
    get_playlist_for_playback,
    get_user_playlists,
    playlist_to_detail,
    playlist_to_detail_enriched,
    remove_track_from_playlist,
    reorder_playlist_tracks,
)

router = APIRouter(tags=["Playlists"])


class CreatePlaylistBody(BaseModel):
    title: str = Field(..., min_length=1)
    description: str | None = None
    is_public: bool = False


class AddTrackBody(BaseModel):
    song_id: int = Field(..., ge=1)


class ReorderBody(BaseModel):
    ordered_song_ids: list[int] = Field(..., min_length=0)


def _map_playlist_errors(exc: Exception) -> HTTPException:
    if isinstance(exc, PlaylistNotFoundError):
        return HTTPException(status_code=404, detail="Playlist not found")
    if isinstance(exc, PlaylistForbiddenError):
        return HTTPException(status_code=403, detail="Not allowed for this playlist")
    if isinstance(exc, PlaylistValidationError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


@router.post("")
def post_playlist(
    body: CreatePlaylistBody,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    try:
        pl = create_playlist(
            db,
            user_id=int(user.id),
            title=body.title,
            description=body.description,
            is_public=body.is_public,
        )
        db.commit()
        db.refresh(pl)
        return playlist_to_detail(pl)
    except PlaylistValidationError as exc:
        db.rollback()
        raise _map_playlist_errors(exc) from exc


@router.get("")
def get_my_playlists(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    """Current user's playlists (metadata only; excludes soft-deleted)."""
    return {"playlists": get_user_playlists(db, user_id=int(user.id))}


@router.get("/{playlist_id}/play")
def get_playlist_play(
    playlist_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User | None, Depends(get_optional_user)],
):
    """
    Ordered track list for playback helpers (no media URLs, no streaming side effects).
    Public playlists: no auth required. Private: owner only (Bearer JWT).
    """
    try:
        viewer_id = int(user.id) if user is not None else None
        return get_playlist_for_playback(
            db, playlist_id=int(playlist_id), user_id=viewer_id
        )
    except (PlaylistNotFoundError, PlaylistForbiddenError) as exc:
        raise _map_playlist_errors(exc) from exc


@router.get("/{playlist_id}")
def get_playlist_detail(
    playlist_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    try:
        pl = get_playlist(db, playlist_id=int(playlist_id), viewer_user_id=int(user.id))
        return playlist_to_detail_enriched(db, pl)
    except (PlaylistNotFoundError, PlaylistForbiddenError) as exc:
        raise _map_playlist_errors(exc) from exc


@router.post("/{playlist_id}/tracks")
def post_playlist_track(
    playlist_id: int,
    body: AddTrackBody,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    try:
        add_track_to_playlist(
            db,
            playlist_id=int(playlist_id),
            song_id=int(body.song_id),
            owner_user_id=int(user.id),
        )
        db.commit()
        pl = get_playlist(db, playlist_id=int(playlist_id), viewer_user_id=int(user.id))
        return playlist_to_detail(pl)
    except (
        PlaylistNotFoundError,
        PlaylistForbiddenError,
        PlaylistValidationError,
    ) as exc:
        db.rollback()
        raise _map_playlist_errors(exc) from exc


@router.delete("/{playlist_id}/tracks/{song_id}")
def delete_playlist_track(
    playlist_id: int,
    song_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    try:
        remove_track_from_playlist(
            db,
            playlist_id=int(playlist_id),
            song_id=int(song_id),
            owner_user_id=int(user.id),
        )
        db.commit()
        pl = get_playlist(db, playlist_id=int(playlist_id), viewer_user_id=int(user.id))
        return playlist_to_detail(pl)
    except (
        PlaylistNotFoundError,
        PlaylistForbiddenError,
        PlaylistValidationError,
    ) as exc:
        db.rollback()
        raise _map_playlist_errors(exc) from exc


@router.put("/{playlist_id}/reorder")
def put_playlist_reorder(
    playlist_id: int,
    body: ReorderBody,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    try:
        reorder_playlist_tracks(
            db,
            playlist_id=int(playlist_id),
            ordered_song_ids=list(body.ordered_song_ids),
            owner_user_id=int(user.id),
        )
        db.commit()
        pl = get_playlist(db, playlist_id=int(playlist_id), viewer_user_id=int(user.id))
        return playlist_to_detail(pl)
    except (
        PlaylistNotFoundError,
        PlaylistForbiddenError,
        PlaylistValidationError,
    ) as exc:
        db.rollback()
        raise _map_playlist_errors(exc) from exc
