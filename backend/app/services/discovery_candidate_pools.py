"""
Discovery candidate pool builders (V1 foundations).

Read-only helpers: no ranking, scoring, or section assembly.
All pools are restricted to the same playable universe as catalog/streaming APIs.
"""

from __future__ import annotations

import random
from typing import Sequence

from sqlalchemy import asc, desc, func
from sqlalchemy.orm import Session

from app.models.global_listening_aggregate import GlobalListeningAggregate
from app.models.listening_aggregate import ListeningAggregate
from app.models.song import Song
from app.models.song_media_asset import (
    SONG_MEDIA_KIND_MASTER_AUDIO,
    SongMediaAsset,
)

_POPULAR_LIMIT = 200
_USER_CANDIDATES_LIMIT = 150
_LOW_EXPOSURE_LIMIT = 200
_RANDOM_CAP = 500


def get_popular_candidates(db: Session) -> list[int]:
    """
    Popular pool: global validated listening mass, newest playable ties irrelevant.

    Source: GlobalListeningAggregate.total_duration DESC.
    Restricted to playable universe via INNER JOIN Song + master asset.

    ``Song.id ASC`` final tie-break ensures stable ordering when durations match.
    """
    rows = (
        db.query(GlobalListeningAggregate.song_id)
        .join(Song, Song.id == GlobalListeningAggregate.song_id)
        .join(
            SongMediaAsset,
            (SongMediaAsset.song_id == Song.id)
            & (SongMediaAsset.kind == SONG_MEDIA_KIND_MASTER_AUDIO),
        )
        .filter(
            GlobalListeningAggregate.song_id.isnot(None),
            Song.upload_status == "ready",
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

    rows = (
        db.query(ListeningAggregate.song_id)
        .join(Song, Song.id == ListeningAggregate.song_id)
        .join(
            SongMediaAsset,
            (SongMediaAsset.song_id == Song.id)
            & (SongMediaAsset.kind == SONG_MEDIA_KIND_MASTER_AUDIO),
        )
        .filter(
            ListeningAggregate.user_id == int(user_id),
            ListeningAggregate.song_id.isnot(None),
            Song.upload_status == "ready",
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
    duration_coalesce = func.coalesce(GlobalListeningAggregate.total_duration, 0)

    rows = (
        db.query(Song.id)
        .outerjoin(
            GlobalListeningAggregate,
            GlobalListeningAggregate.song_id == Song.id,
        )
        .join(
            SongMediaAsset,
            (SongMediaAsset.song_id == Song.id)
            & (SongMediaAsset.kind == SONG_MEDIA_KIND_MASTER_AUDIO),
        )
        .filter(Song.upload_status == "ready")
        .order_by(asc(duration_coalesce), desc(Song.created_at), Song.id.asc())
        .limit(_LOW_EXPOSURE_LIMIT)
        .all()
    )
    return [int(r[0]) for r in rows]


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
