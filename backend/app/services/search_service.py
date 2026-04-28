from __future__ import annotations

from typing import Any

from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session

from app.models.artist import Artist
from app.models.release import RELEASE_STATE_PUBLISHED, Release
from app.models.song import Song

_MAX_QUERY_LEN = 128
_DEFAULT_TOTAL_LIMIT = 10
_MAX_TOTAL_LIMIT = 25
_SIDE_ENTITY_LIMIT = 5


def _escape_like_pattern(s: str) -> str:
    """Escape ``%``, ``_``, and ``\\`` for SQL LIKE with ESCAPE '\\'."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _normalized_query(raw: str) -> str:
    trimmed = (raw or "").strip()
    if len(trimmed) > _MAX_QUERY_LEN:
        trimmed = trimmed[:_MAX_QUERY_LEN]
    return trimmed


def _rank_case(column: Any, normalized_q: str):
    escaped = _escape_like_pattern(normalized_q)
    q_prefix = f"{escaped}%"
    q_partial = f"%{escaped}%"
    lowered = func.lower(column)
    return case(
        (lowered == normalized_q, 1),
        (lowered.like(q_prefix, escape="\\"), 2),
        else_=3,
    ), q_partial


def _text_rank(normalized_q: str, text: str) -> int:
    q = normalized_q.strip().lower()
    t = (text or "").strip().lower()
    if not q or not t:
        return 4
    if t == q:
        return 1
    if t.startswith(q):
        return 2
    if q in t:
        return 3
    return 4


def search_artists(db: Session, query: str, limit: int) -> list[dict[str, Any]]:
    normalized = _normalized_query(query).lower()
    if len(normalized) < 2 or int(limit) < 1:
        return []
    rank_expr, q_partial = _rank_case(Artist.name, normalized)
    rows = (
        db.query(Artist)
        .filter(
            Artist.is_system.is_(False),
            func.lower(Artist.name).like(q_partial, escape="\\"),
        )
        .order_by(rank_expr.asc(), Artist.name.asc())
        .limit(int(limit))
        .all()
    )
    return [
        {
            "type": "artist",
            "id": int(a.id),
            "name": str(a.name or "").strip(),
            "slug": str(a.slug or "").strip(),
        }
        for a in rows
    ]


def search_tracks(db: Session, query: str, limit: int) -> list[dict[str, Any]]:
    normalized = _normalized_query(query).lower()
    if len(normalized) < 2 or int(limit) < 1:
        return []
    escaped = _escape_like_pattern(normalized)
    q_prefix = f"{escaped}%"
    q_partial = f"%{escaped}%"
    title_lower = func.lower(Song.title)
    artist_lower = func.lower(Artist.name)
    album_lower = func.lower(Release.title)
    rank_expr = case(
        (title_lower == normalized, 1),
        (artist_lower == normalized, 1),
        (album_lower == normalized, 1),
        (title_lower.like(q_prefix, escape="\\"), 2),
        (artist_lower.like(q_prefix, escape="\\"), 2),
        (album_lower.like(q_prefix, escape="\\"), 2),
        else_=3,
    )
    rows = (
        db.query(Song, Artist, Release)
        .join(Artist, Artist.id == Song.artist_id)
        .join(Release, Release.id == Song.release_id)
        .filter(
            Song.deleted_at.is_(None),
            Song.title.isnot(None),
            Song.upload_status == "ready",
            Release.state == RELEASE_STATE_PUBLISHED,
            Artist.is_system.is_(False),
            or_(
                title_lower.like(q_partial, escape="\\"),
                artist_lower.like(q_partial, escape="\\"),
                album_lower.like(q_partial, escape="\\"),
            ),
        )
        .order_by(rank_expr.asc(), Song.title.asc())
        .limit(int(limit))
        .all()
    )
    payload: list[dict[str, Any]] = []
    for song, artist, release in rows:
        payload.append(
            {
                "type": "track",
                "id": int(song.id),
                "title": str(song.title or "").strip(),
                "slug": str(song.slug or "").strip(),
                "artist": {
                    "id": int(artist.id),
                    "name": str(artist.name or "").strip(),
                    "slug": str(artist.slug or "").strip(),
                },
                "album": {
                    "id": int(release.id),
                    "title": str(release.title or "").strip(),
                    "slug": str(release.slug or "").strip(),
                }
                if release is not None
                else None,
            }
        )
    return payload


def search_albums(db: Session, query: str, limit: int) -> list[dict[str, Any]]:
    normalized = _normalized_query(query).lower()
    if len(normalized) < 2 or int(limit) < 1:
        return []
    rank_expr, q_partial = _rank_case(Release.title, normalized)
    rows = (
        db.query(Release, Artist)
        .join(Artist, Artist.id == Release.artist_id)
        .filter(
            Release.state == RELEASE_STATE_PUBLISHED,
            Artist.is_system.is_(False),
            func.lower(Release.title).like(q_partial, escape="\\"),
        )
        .order_by(rank_expr.asc(), Release.title.asc())
        .limit(int(limit))
        .all()
    )
    payload: list[dict[str, Any]] = []
    for release, artist in rows:
        payload.append(
            {
                "type": "album",
                "id": int(release.id),
                "title": str(release.title or "").strip(),
                "slug": str(release.slug or "").strip(),
                "artist": {
                    "id": int(artist.id),
                    "name": str(artist.name or "").strip(),
                    "slug": str(artist.slug or "").strip(),
                },
            }
        )
    return payload


def search_global(db: Session, query: str, limit: int = _DEFAULT_TOTAL_LIMIT) -> dict[str, Any]:
    trimmed = _normalized_query(query)
    safe_limit = max(1, min(int(limit or _DEFAULT_TOTAL_LIMIT), _MAX_TOTAL_LIMIT))
    if len(trimmed) < 2:
        return {
            "results": [],
            "groups": {"artists": [], "tracks": [], "albums": []},
            "meta": {"query": trimmed, "limit": safe_limit},
        }

    tracks = search_tracks(db, trimmed, safe_limit)
    artists = search_artists(db, trimmed, _SIDE_ENTITY_LIMIT)
    albums = search_albums(db, trimmed, _SIDE_ENTITY_LIMIT)
    print("tracks:", len(tracks))
    print("artists:", len(artists))
    print("albums:", len(albums))
    ranked = [*tracks, *artists, *albums]

    return {
        "results": ranked,
        "groups": {
            "artists": artists,
            "tracks": tracks,
            "albums": albums,
        },
        "meta": {
            "query": trimmed,
            "limit": safe_limit,
        },
    }
