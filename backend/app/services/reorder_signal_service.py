"""Runtime aggregation of playlist reorder signals for discovery (weak, capped)."""

from __future__ import annotations

import logging
import math
import os
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import and_, case as sql_case, func

from app.models.playlist import Playlist
from app.models.playlist_reorder_event import PlaylistReorderEvent
from app.services.like_service import LIKED_SONGS_PLAYLIST_TITLE

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_REORDER_SIGNAL_WINDOW_DAYS = 14
_REORDER_POSITIVE_SUM_CAP = 20


def _reorder_signal_debug_enabled() -> bool:
    return os.getenv("HM_DEBUG_REORDER_SIGNAL", "").strip().lower() in {"1", "true", "yes"}


def _liked_playlist_match() -> tuple:
    """SQL predicate: private playlist titled like the canonical Liked Songs playlist."""
    return and_(Playlist.is_public.is_(False), Playlist.title == LIKED_SONGS_PLAYLIST_TITLE)


def _weighted_delta_column():
    """Per-event: min(delta, 5) * (0.4 if liked else 1.0). Portable (no SQL LEAST)."""
    d = PlaylistReorderEvent.delta_position
    clamped = sql_case((d <= 5, d), else_=5)
    return clamped * sql_case((_liked_playlist_match(), 0.4), else_=1.0)


def _reorder_base_query(db: "Session", uid: int, ids: list[int], cutoff: datetime):
    weighted = _weighted_delta_column()
    return (
        db.query(PlaylistReorderEvent.song_id, func.sum(weighted).label("wsum"))
        .select_from(PlaylistReorderEvent)
        .join(Playlist, Playlist.id == PlaylistReorderEvent.playlist_id)
        .filter(
            PlaylistReorderEvent.user_id == uid,
            PlaylistReorderEvent.song_id.in_(ids),
            PlaylistReorderEvent.created_at >= cutoff,
            PlaylistReorderEvent.delta_position > 0,
            Playlist.deleted_at.is_(None),
            Playlist.owner_user_id == PlaylistReorderEvent.user_id,
        )
        .group_by(PlaylistReorderEvent.song_id)
    )


def _log_debug_top_playlists(
    db: "Session",
    *,
    uid: int,
    song_ids: list[int],
    cutoff: datetime,
    signal_by_song: dict[int, float],
) -> None:
    if not signal_by_song:
        return
    weighted = _weighted_delta_column()
    rows = (
        db.query(
            PlaylistReorderEvent.song_id,
            PlaylistReorderEvent.playlist_id,
            func.sum(weighted).label("contrib"),
        )
        .select_from(PlaylistReorderEvent)
        .join(Playlist, Playlist.id == PlaylistReorderEvent.playlist_id)
        .filter(
            PlaylistReorderEvent.user_id == uid,
            PlaylistReorderEvent.song_id.in_(song_ids),
            PlaylistReorderEvent.created_at >= cutoff,
            PlaylistReorderEvent.delta_position > 0,
            Playlist.deleted_at.is_(None),
            Playlist.owner_user_id == PlaylistReorderEvent.user_id,
        )
        .group_by(PlaylistReorderEvent.song_id, PlaylistReorderEvent.playlist_id)
        .all()
    )
    best: dict[int, tuple[int, float]] = {}
    for sid, pid, contrib in rows:
        if sid is None or pid is None:
            continue
        c = float(contrib or 0.0)
        if int(sid) not in signal_by_song:
            continue
        cur = best.get(int(sid))
        if cur is None or c > cur[1]:
            best[int(sid)] = (int(pid), c)
    top_by_song = {sid: best[sid][0] for sid in best}
    logger.info(
        "reorder_signal_debug top_playlist_id_by_song user_id=%s map=%s",
        uid,
        top_by_song,
    )


def load_reorder_signal_by_song(
    db: "Session",
    user_id: int | None,
    song_ids: list[int],
) -> dict[int, float]:
    """
    Per ``song_id``, capped log signal from recent positive reorder gestures.

    Joins ``playlists`` (non-deleted, owner matches event user). Per event contributes
    ``LEAST(delta_position, 5)`` times **0.4** for private **Liked Songs** title match
    (see ``LIKED_SONGS_PLAYLIST_TITLE``), else **1.0**. Sums over the last **14** days,
    then ``min(sum, 20)`` and ``log1p`` in Python. Anonymous or empty ``song_ids`` → ``{}``.

    When env ``HM_DEBUG_REORDER_SIGNAL`` is truthy, logs top contributing ``playlist_id``
    per song (keys are songs with a non-zero signal only).
    """
    if user_id is None or not song_ids:
        return {}

    uid = int(user_id)
    ids = [int(s) for s in song_ids]
    cutoff = datetime.utcnow() - timedelta(days=_REORDER_SIGNAL_WINDOW_DAYS)

    rows = _reorder_base_query(db, uid, ids, cutoff).all()

    out: dict[int, float] = {}
    for sid, raw_sum in rows:
        if sid is None:
            continue
        positive_sum = min(float(raw_sum or 0.0), float(_REORDER_POSITIVE_SUM_CAP))
        if positive_sum <= 0.0:
            continue
        out[int(sid)] = float(math.log1p(positive_sum))

    if _reorder_signal_debug_enabled():
        _log_debug_top_playlists(db, uid=uid, song_ids=ids, cutoff=cutoff, signal_by_song=out)

    return out
