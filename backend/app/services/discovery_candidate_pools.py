"""
Discovery candidate pool builders (V1 foundations).

Read-only helpers: no ranking, scoring, or section assembly.
All pools are restricted to the same playable universe as catalog/streaming APIs.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime
from typing import Sequence

from sqlalchemy import and_, asc, desc, func, or_
from sqlalchemy.orm import Session

from app.models.global_listening_aggregate import GlobalListeningAggregate
from app.models.listening_aggregate import ListeningAggregate
from app.models.playlist import Playlist, PlaylistTrack
from app.models.release import RELEASE_STATE_PUBLISHED, Release
from app.models.song import Song
from app.models.song_media_asset import (
    SONG_MEDIA_KIND_MASTER_AUDIO,
    SongMediaAsset,
)

_POPULAR_LIMIT = 200
_USER_CANDIDATES_LIMIT = 150
_LOW_EXPOSURE_LIMIT = 200
_RANDOM_CAP = 500


def _utc_now_naive() -> datetime:
    # DB columns are currently naive datetimes in local dev.
    return datetime.now(UTC).replace(tzinfo=None)


def _release_visible_sql(now: datetime):
    return and_(
        Song.release_id.isnot(None),
        Release.id.isnot(None),
        Release.state == RELEASE_STATE_PUBLISHED,
        Release.discoverable_at.isnot(None),
        Release.discoverable_at <= now,
    )


def _song_discoverable_sql(now: datetime):
    # Legacy songs without release_id stay discoverable via upload_status="ready".
    return and_(
        Song.deleted_at.is_(None),
        Song.upload_status == "ready",
        or_(Song.release_id.is_(None), _release_visible_sql(now)),
    )


def get_discovery_visibility_stats(db: Session) -> dict[str, int]:
    now = _utc_now_naive()
    base = (
        db.query(Song.id, Song.release_id, Release.id.label("release_row_id"))
        .join(
            SongMediaAsset,
            (SongMediaAsset.song_id == Song.id)
            & (SongMediaAsset.kind == SONG_MEDIA_KIND_MASTER_AUDIO),
        )
        .outerjoin(Release, Release.id == Song.release_id)
        .filter(Song.upload_status == "ready", Song.deleted_at.is_(None))
    )
    songs_with_release = int(base.filter(Song.release_id.isnot(None)).count() or 0)
    songs_without_release = int(base.filter(Song.release_id.is_(None)).count() or 0)
    filtered_by_release_gating = int(
        base.filter(Song.release_id.isnot(None), ~_release_visible_sql(now)).count() or 0
    )
    return {
        "songs_with_release": songs_with_release,
        "songs_without_release": songs_without_release,
        "songs_filtered_by_release_gating": filtered_by_release_gating,
    }


def get_popular_candidates(db: Session) -> list[int]:
    """
    Popular pool: global validated listening mass, newest playable ties irrelevant.

    Source: GlobalListeningAggregate.total_duration DESC.
    Restricted to playable universe via INNER JOIN Song + master asset.

    ``Song.id ASC`` final tie-break ensures stable ordering when durations match.
    """
    now = _utc_now_naive()
    rows = (
        db.query(GlobalListeningAggregate.song_id)
        .join(Song, Song.id == GlobalListeningAggregate.song_id)
        .outerjoin(Release, Release.id == Song.release_id)
        .join(
            SongMediaAsset,
            (SongMediaAsset.song_id == Song.id)
            & (SongMediaAsset.kind == SONG_MEDIA_KIND_MASTER_AUDIO),
        )
        .filter(
            GlobalListeningAggregate.song_id.isnot(None),
            _song_discoverable_sql(now),
        )
        .order_by(desc(GlobalListeningAggregate.total_duration), Song.id.asc())
        .limit(_POPULAR_LIMIT)
        .all()
    )
    return [int(r[0]) for r in rows]


def get_user_candidates(db: Session, user_id: int | None) -> list[int]:
    """
    User affinity pool from per-user aggregates (no raw ListeningEvent scans).

    If ``user_id`` is None (anonymous), returns [].

    ``Song.id ASC`` final tie-break ensures stable ordering when durations match.
    """
    if user_id is None:
        return []

    now = _utc_now_naive()
    rows = (
        db.query(ListeningAggregate.song_id)
        .join(Song, Song.id == ListeningAggregate.song_id)
        .outerjoin(Release, Release.id == Song.release_id)
        .join(
            SongMediaAsset,
            (SongMediaAsset.song_id == Song.id)
            & (SongMediaAsset.kind == SONG_MEDIA_KIND_MASTER_AUDIO),
        )
        .filter(
            ListeningAggregate.user_id == int(user_id),
            ListeningAggregate.song_id.isnot(None),
            _song_discoverable_sql(now),
        )
        .order_by(desc(ListeningAggregate.total_duration), Song.id.asc())
        .limit(_USER_CANDIDATES_LIMIT)
        .all()
    )
    return [int(r[0]) for r in rows]


def get_low_exposure_candidates(db: Session) -> list[int]:
    """
    Low global exposure among playable songs, with recency tie-break.

    LEFT JOIN global aggregate so never-heard (NULL) sorts as zero exposure.

    ``Song.id ASC`` final tie-break ensures stable ordering when exposure and
    ``created_at`` match.
    """
    now = _utc_now_naive()
    duration_coalesce = func.coalesce(GlobalListeningAggregate.total_duration, 0)

    rows = (
        db.query(Song.id)
        .outerjoin(
            GlobalListeningAggregate,
            GlobalListeningAggregate.song_id == Song.id,
        )
        .outerjoin(Release, Release.id == Song.release_id)
        .join(
            SongMediaAsset,
            (SongMediaAsset.song_id == Song.id)
            & (SongMediaAsset.kind == SONG_MEDIA_KIND_MASTER_AUDIO),
        )
        .filter(_song_discoverable_sql(now))
        .order_by(asc(duration_coalesce), desc(Song.created_at), Song.id.asc())
        .limit(_LOW_EXPOSURE_LIMIT)
        .all()
    )
    return [int(r[0]) for r in rows]


def get_playlist_candidates(db: Session, user_id: int | None) -> list[int]:
    """
    Tracks drawn from **public** playlists only, ordered by playlist ``updated_at`` DESC.

    For each playlist (in that order), append up to **3** tracks that pass the same
    playable-universe filters as other pools (master audio + ``_song_discoverable_sql``).
    ``user_id`` is accepted for API symmetry; visibility is **public playlists only**
    today (not personalized).

    Ordering is deterministic: playlists ``updated_at DESC``, ``Playlist.id ASC`` tie-break;
    tracks ``position ASC``, ``PlaylistTrack.id ASC``.     Duplicate ``song_id``s may appear
    across playlists; ``build_candidate_set`` dedupes by first occurrence.
    """
    _ = user_id  # reserved for future personalization; public playlists only today.
    now = _utc_now_naive()
    playlist_ids = [
        int(r[0])
        for r in (
            db.query(Playlist.id)
            .filter(
                Playlist.deleted_at.is_(None),
                Playlist.is_public.is_(True),
            )
            .order_by(desc(Playlist.updated_at), Playlist.id.asc())
            .all()
        )
    ]
    out: list[int] = []
    for pid in playlist_ids:
        rows = (
            db.query(PlaylistTrack.song_id)
            .join(Song, Song.id == PlaylistTrack.song_id)
            .outerjoin(Release, Release.id == Song.release_id)
            .join(
                SongMediaAsset,
                (SongMediaAsset.song_id == Song.id)
                & (SongMediaAsset.kind == SONG_MEDIA_KIND_MASTER_AUDIO),
            )
            .filter(
                PlaylistTrack.playlist_id == int(pid),
                _song_discoverable_sql(now),
            )
            .order_by(PlaylistTrack.position.asc(), PlaylistTrack.id.asc())
            .limit(3)
            .all()
        )
        for (song_id,) in rows:
            out.append(int(song_id))
    return out


def get_random_candidates(base_ids: Sequence[int]) -> list[int]:
    """
    Entropy bucket: shuffle union of prior pool ids in Python (no ORDER BY RANDOM()).

    Order is not seeded; Step 2+ may pass a local RNG or seed when rotation is defined.
    """
    unique: list[int] = []
    seen: set[int] = set()
    for sid in base_ids:
        i = int(sid)
        if i not in seen:
            seen.add(i)
            unique.append(i)
    if not unique:
        return []
    shuffled = unique[:]
    random.shuffle(shuffled)
    return shuffled[:_RANDOM_CAP]
