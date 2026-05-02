"""User likes: explicit events + private ``Liked Songs`` playlist sync."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services.like_service import LikeValidationError, like_song, unlike_song

router = APIRouter(tags=["likes"])


class LikeBody(BaseModel):
    song_id: int = Field(..., ge=1)


@router.post("/like")
def post_like(
    body: LikeBody,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    try:
        out = like_song(db, user_id=int(user.id), song_id=int(body.song_id))
        db.commit()
        return out
    except LikeValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/like")
def delete_like(
    song_id: Annotated[int, Query(..., ge=1)],
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    out = unlike_song(db, user_id=int(user.id), song_id=int(song_id))
    db.commit()
    return out
