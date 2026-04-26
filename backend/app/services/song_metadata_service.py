from __future__ import annotations

import logging
from typing import Sequence

from sqlalchemy.orm import Session

from app.models.artist import Artist
from app.models.genre import Genre
from app.models.song import Song
from app.models.song_credit_entry import CREDIT_ROLE_VALUES, SongCreditEntry
from app.models.subgenre import Subgenre
from app.models.song_artist_split import SongArtistSplit
from app.models.song_featured_artist import SongFeaturedArtist
from app.services.release_service import bind_song_to_release, create_single_release_for_song
from app.services.song_artist_split_service import set_splits_for_song
from app.services.song_metadata_validation import (
    validate_country_code,
    validate_genre_subgenre_pair,
)
from app.services.slug_service import ensure_song_slug, update_song_slug
from app.services.song_state_service import sync_song_state_from_upload_status

logger = logging.getLogger(__name__)

_MAX_FEATURED = 20
_MAX_CREDITS = 20
_MAX_MOODS = 10
_MAX_MOOD_LEN = 32
_MAX_CITY_LEN = 128


def _normalize_moods(raw: Sequence[str] | None) -> list[str] | None:
    """Trim, drop empty, cap count and per-item length; None if no tags remain."""
    if raw is None:
        return None
    out: list[str] = []
    for item in raw:
        s = str(item).strip()
        if not s:
            continue
        out.append(s[:_MAX_MOOD_LEN])
        if len(out) >= _MAX_MOODS:
            break
    return out or None


def _normalize_country_code(country_code: str | None) -> str | None:
    if country_code is None:
        return None
    s = str(country_code).strip().upper()
    if not s:
        return None
    ok, reason = validate_country_code(s)
    if not ok:
        raise ValueError(reason or "invalid_country_code")
    return s


def _normalize_city(city: str | None) -> str | None:
    if city is None:
        return None
    s = str(city).strip()
    if not s:
        return None
    return s[:_MAX_CITY_LEN]


def _validate_song_genre_fields(
    db: Session,
    *,
    genre_id: int | None,
    subgenre_id: int | None,
) -> None:
    ok, reason = validate_genre_subgenre_pair(genre_id=genre_id, subgenre_id=subgenre_id)
    if not ok:
        raise ValueError(reason or "invalid_genre_subgenre_pair")
    if genre_id is not None:
        if db.query(Genre.id).filter(Genre.id == int(genre_id)).first() is None:
            raise ValueError(f"Unknown genre_id: {genre_id}.")
    if subgenre_id is not None:
        row = db.query(Subgenre).filter(Subgenre.id == int(subgenre_id)).first()
        if row is None:
            raise ValueError(f"Unknown subgenre_id: {subgenre_id}.")
        if genre_id is None or int(row.genre_id) != int(genre_id):
            raise ValueError("subgenre_id does not belong to genre_id.")


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
    release_id: int | None = None,
    featured_artist_ids: Sequence[int] | None = None,
    credits: Sequence[dict] | None = None,
    genre_id: int | None = None,
    subgenre_id: int | None = None,
    moods: Sequence[str] | None = None,
    country_code: str | None = None,
    city: str | None = None,
) -> Song:
    """
    Create a song row (draft) with optional featuring artists and credits.

    If the song has no ``SongArtistSplit`` rows yet, inserts a default 100%
    split for the primary artist via :func:`set_splits_for_song`.

    Does not touch file_path, streaming, or payouts.
    """
    cleaned_title = (title or "").strip()
    if not cleaned_title:
        raise ValueError("Title is required")

    primary_id = int(artist_id)
    if db.query(Artist.id).filter(Artist.id == primary_id).first() is None:
        raise ValueError(f"Artist {primary_id} not found.")

    featured = list(featured_artist_ids or [])
    credit_rows = list(credits or [])

    _validate_song_genre_fields(db, genre_id=genre_id, subgenre_id=subgenre_id)

    moods_norm = _normalize_moods(moods)
    country_norm = _normalize_country_code(country_code)
    city_norm = _normalize_city(city)

    song = Song(
        artist_id=primary_id,
        title=cleaned_title,
        genre_id=int(genre_id) if genre_id is not None else None,
        subgenre_id=int(subgenre_id) if subgenre_id is not None else None,
        moods=moods_norm,
        country_code=country_norm,
        city=city_norm,
    )
    db.add(song)
    db.flush()
    ensure_song_slug(db, song, title_source=cleaned_title)
    sync_song_state_from_upload_status(song)
    if release_id is not None:
        bind_song_to_release(db, song=song, release_id=int(release_id))
    else:
        create_single_release_for_song(db, song=song)

    replace_song_featured_artists(db, int(song.id), primary_id, featured)
    replace_song_credit_entries(db, int(song.id), credit_rows)

    sid = int(song.id)
    has_splits = (
        db.query(SongArtistSplit.id).filter(SongArtistSplit.song_id == sid).first()
        is not None
    )
    if not has_splits:
        set_splits_for_song(
            db,
            sid,
            [{"artist_id": primary_id, "share": 1.0}],
            commit=False,
        )

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


def _featured_ids_for_song(db: Session, song_id: int) -> list[int]:
    rows = (
        db.query(SongFeaturedArtist.artist_id)
        .filter(SongFeaturedArtist.song_id == int(song_id))
        .order_by(SongFeaturedArtist.position.asc())
        .all()
    )
    return [int(r[0]) for r in rows]


def update_existing_song_metadata(
    db: Session,
    song_id: int,
    *,
    title: str,
    featured_artist_ids: Sequence[int],
    credits: Sequence[dict],
    genre_id: int | None,
    subgenre_id: int | None,
    moods: Sequence[str] | None,
    country_code: str | None,
    city: str | None,
) -> Song:
    """
    Replace metadata on an existing song (upload wizard / catalog edit).

    When ``upload_status == "ready"``, title and featuring artists cannot
    change; attempts to change them raise ``ValueError``.
    """
    song = (
        db.query(Song)
        .filter(Song.id == int(song_id), Song.deleted_at.is_(None))
        .first()
    )
    if song is None:
        raise ValueError(f"Song {song_id} not found.")

    primary_id = int(song.artist_id)
    lock = str(song.upload_status or "").strip().lower() == "ready"

    if lock:
        want_title = (title or "").strip()
        if want_title != (song.title or "").strip():
            raise ValueError("title_locked")
        if list(featured_artist_ids) != _featured_ids_for_song(db, int(song_id)):
            raise ValueError("featured_locked")
    else:
        cleaned_title = (title or "").strip()
        if not cleaned_title:
            raise ValueError("Title is required")
        song.title = cleaned_title
        update_song_slug(db, song, title_source=cleaned_title)
        replace_song_featured_artists(db, int(song_id), primary_id, featured_artist_ids)

    _validate_song_genre_fields(db, genre_id=genre_id, subgenre_id=subgenre_id)

    moods_norm = _normalize_moods(moods)
    country_norm = _normalize_country_code(country_code)
    city_norm = _normalize_city(city)

    song.genre_id = int(genre_id) if genre_id is not None else None
    song.subgenre_id = int(subgenre_id) if subgenre_id is not None else None
    song.moods = moods_norm
    song.country_code = country_norm
    song.city = city_norm

    replace_song_credit_entries(db, int(song_id), list(credits))

    sync_song_state_from_upload_status(song)
    db.commit()
    db.refresh(song)

    logger.info(
        "song_metadata_updated",
        extra={"song_id": int(song_id), "locked": lock},
    )
    return song
