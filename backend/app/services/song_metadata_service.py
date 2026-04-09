from __future__ import annotations

import logging
from typing import Sequence

from sqlalchemy.orm import Session

from app.models.artist import Artist
from app.models.song import Song
from app.models.song_credit_entry import CREDIT_ROLE_VALUES, SongCreditEntry
from app.models.song_featured_artist import SongFeaturedArtist

logger = logging.getLogger(__name__)

_MAX_FEATURED = 20
_MAX_CREDITS = 20


def _validate_featured_artist_ids(
    db: Session,
    song_primary_artist_id: int,
    featured_artist_ids: Sequence[int],
) -> list[int]:
    if len(featured_artist_ids) > _MAX_FEATURED:
        raise ValueError(f"At most {_MAX_FEATURED} featuring artists allowed.")

    seen: set[int] = set()
    ordered: list[int] = []
    for raw in featured_artist_ids:
        aid = int(raw)
        if aid in seen:
            raise ValueError(f"Duplicate featured artist_id: {aid}.")
        seen.add(aid)
        ordered.append(aid)

    if song_primary_artist_id in seen:
        raise ValueError("Featured artists must not include the song's primary artist_id.")

    if not ordered:
        return []

    rows = db.query(Artist.id).filter(Artist.id.in_(ordered)).all()
    found = {int(r[0]) for r in rows}
    missing = [i for i in ordered if i not in found]
    if missing:
        raise ValueError(f"Unknown artist_id(s): {missing}.")

    return ordered


def _validate_credits(credits: Sequence[dict]) -> list[tuple[str, str]]:
    if len(credits) > _MAX_CREDITS:
        raise ValueError(f"At most {_MAX_CREDITS} credit entries allowed.")

    allowed = set(CREDIT_ROLE_VALUES)
    out: list[tuple[str, str]] = []
    for row in credits:
        if not isinstance(row, dict):
            raise ValueError("Each credit must be an object with name and role.")
        name = (row.get("name") or "").strip()
        role = row.get("role")
        if not name:
            raise ValueError("Each credit must have a non-empty name.")
        if role is None or str(role).strip() == "":
            raise ValueError("Each credit must have a role.")
        role_s = str(role).strip()
        if role_s not in allowed:
            raise ValueError(
                f"Invalid credit role {role_s!r}; allowed: {sorted(allowed)}."
            )
        out.append((name, role_s))
    return out


def replace_song_featured_artists(
    db: Session,
    song_id: int,
    primary_artist_id: int,
    featured_artist_ids: Sequence[int],
) -> None:
    ordered = _validate_featured_artist_ids(db, primary_artist_id, featured_artist_ids)
    db.query(SongFeaturedArtist).filter(SongFeaturedArtist.song_id == int(song_id)).delete(
        synchronize_session=False
    )
    for pos, aid in enumerate(ordered, start=1):
        db.add(
            SongFeaturedArtist(
                song_id=int(song_id),
                artist_id=int(aid),
                position=pos,
            )
        )


def replace_song_credit_entries(
    db: Session,
    song_id: int,
    credits: Sequence[dict],
) -> None:
    normalized = _validate_credits(credits)
    db.query(SongCreditEntry).filter(SongCreditEntry.song_id == int(song_id)).delete(
        synchronize_session=False
    )
    for position, (name, role_s) in enumerate(normalized, start=1):
        db.add(
            SongCreditEntry(
                song_id=int(song_id),
                position=position,
                display_name=name,
                role=role_s,
            )
        )


def create_song_with_metadata(
    db: Session,
    *,
    title: str,
    artist_id: int,
    featured_artist_ids: Sequence[int] | None = None,
    credits: Sequence[dict] | None = None,
) -> Song:
    """
    Create a song row (draft) with optional featuring artists and credits.
    Does not touch file_path, splits, streaming, or payouts.
    """
    cleaned_title = (title or "").strip()
    if not cleaned_title:
        raise ValueError("title is required.")

    primary_id = int(artist_id)
    if db.query(Artist.id).filter(Artist.id == primary_id).first() is None:
        raise ValueError(f"Artist {primary_id} not found.")

    featured = list(featured_artist_ids or [])
    credit_rows = list(credits or [])

    song = Song(artist_id=primary_id, title=cleaned_title)
    db.add(song)
    db.flush()

    replace_song_featured_artists(db, int(song.id), primary_id, featured)
    replace_song_credit_entries(db, int(song.id), credit_rows)

    db.commit()
    db.refresh(song)

    logger.info(
        "song_created_with_metadata",
        extra={
            "song_id": int(song.id),
            "artist_id": int(song.artist_id),
            "featured_count": len(featured),
            "credits_count": len(credit_rows),
        },
    )
    return song
