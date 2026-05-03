"""Playlist CRUD (MVP). Reorder events feed discovery read-side signals only; no curator economics or streaming integration."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import case, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.playlist import Playlist, PlaylistTrack
from app.models.playlist_reorder_event import PlaylistReorderEvent
from app.models.song import Song
from app.services.discovery_hydration import (
    build_placeholder,
    hydrate_songs_batch_for_playlist,
)
from app.services.discovery_row_normalize import normalize_discovery_track_row


class PlaylistNotFoundError(Exception):
    """Playlist missing or soft-deleted."""


class PlaylistForbiddenError(Exception):
    """Caller cannot access or mutate this playlist."""


class PlaylistValidationError(Exception):
    """Invalid input or conflicting state (business rules)."""


def _touch_playlist_updated_at(playlist: Playlist) -> None:
    playlist.updated_at = datetime.utcnow()


def _playlist_updated_at_utc_for_event(playlist: Playlist) -> datetime:
    """UTC-aware snapshot aligned with ``Playlist.updated_at`` (naive UTC in DB)."""
    ts = playlist.updated_at
    if ts is None:
        return datetime.now(timezone.utc)
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts


def _compact_positions(db: Session, playlist_id: int) -> None:
    rows = (
        db.query(PlaylistTrack)
        .filter(PlaylistTrack.playlist_id == int(playlist_id))
        .order_by(PlaylistTrack.position.asc(), PlaylistTrack.id.asc())
        .all()
    )
    for i, row in enumerate(rows, start=1):
        if int(row.position) != i:
            row.position = i


def _playlist_query_visible(db: Session, playlist_id: int) -> Playlist | None:
    return (
        db.query(Playlist)
        .filter(
            Playlist.id == int(playlist_id),
            Playlist.deleted_at.is_(None),
        )
        .first()
    )


def _ensure_playlist_owner(playlist: Playlist, user_id: int) -> None:
    if int(playlist.owner_user_id) != int(user_id):
        raise PlaylistForbiddenError()


def _ensure_playable_song(db: Session, song_id: int) -> Song:
    song = (
        db.query(Song)
        .filter(Song.id == int(song_id), Song.deleted_at.is_(None))
        .first()
    )
    if song is None:
        raise PlaylistValidationError("Song not found")
    return song


def create_playlist(
    db: Session,
    *,
    user_id: int,
    title: str,
    description: str | None,
    is_public: bool,
) -> Playlist:
    t = (title or "").strip()
    if not t:
        raise PlaylistValidationError("Title is required")
    desc = (description or "").strip()
    desc_val = desc if desc else None
    now = datetime.utcnow()
    pl = Playlist(
        owner_user_id=int(user_id),
        title=t,
        description=desc_val,
        is_public=bool(is_public),
        created_at=now,
        updated_at=now,
    )
    db.add(pl)
    db.flush()
    return pl


def get_playlist(db: Session, *, playlist_id: int, viewer_user_id: int) -> Playlist:
    pl = _playlist_query_visible(db, playlist_id)
    if pl is None:
        raise PlaylistNotFoundError()
    if not pl.is_public and int(pl.owner_user_id) != int(viewer_user_id):
        raise PlaylistForbiddenError()
    return pl


def get_playlist_for_playback(
    db: Session,
    *,
    playlist_id: int,
    user_id: int | None,
) -> dict:
    """
    Lightweight playback payload: playlist metadata + ordered tracks only.
    ``user_id`` is the authenticated viewer when present; ``None`` for anonymous.
    Public playlists: any caller. Private: owner only.
    """
    pl = _playlist_query_visible(db, playlist_id)
    if pl is None:
        raise PlaylistNotFoundError()
    if not pl.is_public:
        if user_id is None or int(pl.owner_user_id) != int(user_id):
            raise PlaylistForbiddenError()
    rows = (
        db.query(PlaylistTrack.song_id, PlaylistTrack.position)
        .filter(PlaylistTrack.playlist_id == int(playlist_id))
        .order_by(PlaylistTrack.position.asc(), PlaylistTrack.id.asc())
        .all()
    )
    return {
        "playlist": {
            "id": int(pl.id),
            "title": pl.title,
            "owner_user_id": int(pl.owner_user_id),
            "is_public": bool(pl.is_public),
        },
        "tracks": [
            {"song_id": int(sid), "position": int(pos)} for sid, pos in rows
        ],
    }


def add_track_to_playlist(
    db: Session,
    *,
    playlist_id: int,
    song_id: int,
    owner_user_id: int,
) -> PlaylistTrack:
    pl = _playlist_query_visible(db, playlist_id)
    if pl is None:
        raise PlaylistNotFoundError()
    _ensure_playlist_owner(pl, owner_user_id)
    _ensure_playable_song(db, song_id)

    exists = (
        db.query(PlaylistTrack.id)
        .filter(
            PlaylistTrack.playlist_id == int(playlist_id),
            PlaylistTrack.song_id == int(song_id),
        )
        .first()
    )
    if exists is not None:
        raise PlaylistValidationError("Song already in playlist")

    max_pos = (
        db.query(func.coalesce(func.max(PlaylistTrack.position), 0))
        .filter(PlaylistTrack.playlist_id == int(playlist_id))
        .scalar()
    )
    next_pos = int(max_pos or 0) + 1
    row = PlaylistTrack(
        playlist_id=int(playlist_id),
        song_id=int(song_id),
        position=next_pos,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        raise PlaylistValidationError("Could not add track (duplicate or ordering conflict)") from exc
    _touch_playlist_updated_at(pl)
    db.flush()
    return row


def remove_track_from_playlist(
    db: Session,
    *,
    playlist_id: int,
    song_id: int,
    owner_user_id: int,
) -> None:
    pl = _playlist_query_visible(db, playlist_id)
    if pl is None:
        raise PlaylistNotFoundError()
    _ensure_playlist_owner(pl, owner_user_id)

    row = (
        db.query(PlaylistTrack)
        .filter(
            PlaylistTrack.playlist_id == int(playlist_id),
            PlaylistTrack.song_id == int(song_id),
        )
        .first()
    )
    if row is None:
        raise PlaylistValidationError("Song not in playlist")

    db.delete(row)
    db.flush()
    _compact_positions(db, playlist_id)
    _touch_playlist_updated_at(pl)
    db.flush()


def reorder_playlist_tracks(
    db: Session,
    *,
    playlist_id: int,
    ordered_song_ids: list[int],
    owner_user_id: int,
) -> None:
    pl = _playlist_query_visible(db, playlist_id)
    if pl is None:
        raise PlaylistNotFoundError()
    _ensure_playlist_owner(pl, owner_user_id)

    current_rows = (
        db.query(PlaylistTrack)
        .filter(PlaylistTrack.playlist_id == int(playlist_id))
        .order_by(PlaylistTrack.position.asc(), PlaylistTrack.id.asc())
        .all()
    )
    current_ids = [int(r.song_id) for r in current_rows]
    ordered = [int(x) for x in ordered_song_ids]

    if len(ordered) != len(current_ids):
        raise PlaylistValidationError("ordered_song_ids length must match track count")
    if set(ordered) != set(current_ids):
        raise PlaylistValidationError("ordered_song_ids must match playlist tracks")

    old_pos_by_song = {int(r.song_id): int(r.position) for r in current_rows}
    pos_by_song = {sid: i + 1 for i, sid in enumerate(ordered)}
    # Two-phase update avoids UNIQUE(playlist_id, position) violations mid-flush.
    for i, r in enumerate(current_rows):
        r.position = -(i + 1)
    db.flush()
    for r in current_rows:
        r.position = pos_by_song[int(r.song_id)]
    try:
        db.flush()
    except IntegrityError as exc:
        raise PlaylistValidationError("Reorder conflict") from exc

    _touch_playlist_updated_at(pl)
    db.flush()

    uid = int(owner_user_id)
    pid = int(playlist_id)
    now = datetime.utcnow()
    playlist_snap = _playlist_updated_at_utc_for_event(pl)
    reorder_mappings: list[dict] = []
    for sid in ordered:
        sid_int = int(sid)
        old_p = old_pos_by_song[sid_int]
        new_p = pos_by_song[sid_int]
        if old_p == new_p:
            continue
        reorder_mappings.append(
            {
                "user_id": uid,
                "playlist_id": pid,
                "song_id": sid_int,
                "old_position": old_p,
                "new_position": new_p,
                "delta_position": old_p - new_p,
                "playlist_updated_at": playlist_snap,
                "created_at": now,
            }
        )
    if reorder_mappings:
        db.bulk_insert_mappings(PlaylistReorderEvent, reorder_mappings)

    db.flush()


def get_user_playlists(db: Session, *, user_id: int) -> list[dict]:
    """
    Playlist summaries owned by ``user_id`` (``deleted_at`` IS NULL).

    Each item: ``id``, ``title``, ``is_public``, ``thumbnail_urls`` (0–4 public cover path
    strings from the first four tracks by ``position``, same hydration as playlist detail;
    omits null covers — empty playlist → ``[]``).
    """
    uid = int(user_id)
    # "Liked Songs" first (title matches like_service.LIKED_SONGS_PLAYLIST_TITLE), then recency.
    liked_first = case((Playlist.title == "Liked Songs", 0), else_=1)
    rows = (
        db.query(Playlist.id, Playlist.title, Playlist.is_public)
        .filter(Playlist.owner_user_id == uid, Playlist.deleted_at.is_(None))
        .order_by(liked_first, Playlist.updated_at.desc(), Playlist.id.asc())
        .all()
    )
    if not rows:
        return []

    playlist_ids = [int(r[0]) for r in rows]
    track_rows = (
        db.query(PlaylistTrack.playlist_id, PlaylistTrack.song_id)
        .filter(PlaylistTrack.playlist_id.in_(playlist_ids))
        .order_by(
            PlaylistTrack.playlist_id.asc(),
            PlaylistTrack.position.asc(),
            PlaylistTrack.id.asc(),
        )
        .all()
    )

    first_four_song_ids: dict[int, list[int]] = {pid: [] for pid in playlist_ids}
    for pl_id, song_id in track_rows:
        bucket = first_four_song_ids[int(pl_id)]
        if len(bucket) < 4:
            bucket.append(int(song_id))

    batch_ids: list[int] = []
    seen_sid: set[int] = set()
    for pid in playlist_ids:
        for sid in first_four_song_ids[pid]:
            if sid not in seen_sid:
                seen_sid.add(sid)
                batch_ids.append(sid)

    hydrate_map = hydrate_songs_batch_for_playlist(db, batch_ids)

    def thumbnails_for(playlist_id: int) -> list[str]:
        out: list[str] = []
        for sid in first_four_song_ids[playlist_id][:4]:
            row = hydrate_map.get(sid)
            if row is None:
                row = normalize_discovery_track_row(dict(build_placeholder(sid)))
            cu = row.get("cover_url")
            if cu:
                out.append(str(cu))
        return out[:4]

    return [
        {
            "id": int(r[0]),
            "title": r[1],
            "is_public": bool(r[2]),
            "thumbnail_urls": thumbnails_for(int(r[0])),
        }
        for r in rows
    ]


def playlist_to_detail(pl: Playlist) -> dict:
    tracks = sorted(pl.tracks, key=lambda t: (int(t.position), int(t.id)))
    return {
        "id": int(pl.id),
        "owner_user_id": int(pl.owner_user_id),
        "title": pl.title,
        "description": pl.description,
        "is_public": bool(pl.is_public),
        "created_at": pl.created_at.isoformat() if pl.created_at else None,
        "updated_at": pl.updated_at.isoformat() if pl.updated_at else None,
        "tracks": [
            {"song_id": int(t.song_id), "position": int(t.position)} for t in tracks
        ],
    }


def playlist_to_detail_enriched(db: Session, pl: Playlist) -> dict:
    """
    Full playlist detail for ``GET /playlists/{id}``: metadata plus per-track titles,
    artist names, ``cover_url`` / ``audio_url`` (discovery-normalized), and ``cover_urls``
    for the first four tracks by position (null entries allowed).

    Hydration is batched via ``hydrate_songs_batch_for_playlist`` (same URL and
    playability rules as discovery).
    """
    tracks_sorted = sorted(pl.tracks, key=lambda t: (int(t.position), int(t.id)))
    ordered_ids = [int(t.song_id) for t in tracks_sorted]
    hydrate_map = hydrate_songs_batch_for_playlist(db, ordered_ids)

    enriched_tracks: list[dict] = []
    for t in tracks_sorted:
        sid = int(t.song_id)
        pos = int(t.position)
        h = hydrate_map.get(sid)
        if h is None:
            h = normalize_discovery_track_row(dict(build_placeholder(sid)))
        enriched_tracks.append(
            {
                "song_id": sid,
                "position": pos,
                "title": h["title"],
                "artist_name": h["artist_name"],
                "cover_url": h["cover_url"],
                "audio_url": h["audio_url"],
            }
        )

    cover_urls = [row["cover_url"] for row in enriched_tracks[:4]]

    return {
        "id": int(pl.id),
        "owner_user_id": int(pl.owner_user_id),
        "title": pl.title,
        "description": pl.description,
        "is_public": bool(pl.is_public),
        "created_at": pl.created_at.isoformat() if pl.created_at else None,
        "updated_at": pl.updated_at.isoformat() if pl.updated_at else None,
        "cover_urls": cover_urls,
        "tracks": enriched_tracks,
    }
