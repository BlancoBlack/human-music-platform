"""
Pure CPU-side combination of discovery ranking signals (no DB).

Loaders live in ``build_candidate_set`` / ``reorder_signal_service``; this module
only applies the same transforms and weights as ``score_candidates`` historically used.

Signals are grouped into **user** (per requesting user) vs **global** (song-level
aggregates across the platform) layers; ``total.signal_score`` is their sum for ranking.
"""

from __future__ import annotations

import math
from typing import Any, TypedDict


# Must stay aligned with discovery ranking contract (non-economic weak boosts).
PLAYLIST_POPULARITY_ALPHA = 0.05
REORDER_BOOST_ALPHA = 0.02

# Global like signal: single ``log1p`` after optional raw cap; weak vs playlist.
LIKE_BOOST_ALPHA = 0.012
# Soft cap (tunable); when ``LIKE_CAP_ENABLED`` is False, raw count is uncapped before log1p.
LIKE_CAP = 100
LIKE_CAP_ENABLED = True
LIKE_SIGNAL_WINDOW_DAYS = 14
# Likes only count in the loader when ``created_at`` is at least this many minutes old
# (reduces accidental tap / immediate unlike noise).
LIKE_MATURITY_MINUTES = 10
# When the song also has public playlist membership, damp like_boost (playlist + likes correlate).
LIKE_PLAYLIST_CORRELATION_DAMP = 0.7


class _PlaylistSignalBlock(TypedDict):
    raw: int
    signal: float
    boost: float


class _LikesSignalBlock(TypedDict):
    raw: int
    signal: float
    boost: float


class _ReorderSignalBlock(TypedDict):
    signal: float
    boost: float


class _UserSignalsBlock(TypedDict):
    reorder: _ReorderSignalBlock


class _GlobalSignalsBlock(TypedDict):
    playlist: _PlaylistSignalBlock
    likes: _LikesSignalBlock


class _TotalSignalBlock(TypedDict):
    user_signal_score: float
    global_signal_score: float
    signal_score: float


def compute_signal_contributions(
    playlist_count: int,
    reorder_signal: float,
    *,
    like_count: int = 0,
) -> dict[str, Any]:
    """
    Combine global playlist breadth, global like velocity, and user reorder features.

    * ``playlist_count``: raw public playlist membership count (``log1p`` applied here).
    * ``reorder_signal``: value from ``load_reorder_signal_by_song`` — already capped
      and ``log1p`` in the loader; **do not** ``log1p`` again.
    * ``like_count``: raw matured count from ``load_like_signal_by_song``. ``signal`` =
      ``log1p(effective_raw)`` where ``effective_raw`` applies ``LIKE_CAP`` only if
      ``LIKE_CAP_ENABLED``. **Single** ``log1p``. If ``playlist_count > 0``, ``like_boost``
      is multiplied by ``LIKE_PLAYLIST_CORRELATION_DAMP`` (temporary decorrelation).

    Returns ``user`` / ``global`` / ``total`` blocks. Use ``total["signal_score"]``
    for additive use in main ``score`` and ``for_you_score`` (equals
    ``user_signal_score + global_signal_score``).
    """
    pc = int(playlist_count)
    rs = float(reorder_signal)
    lc = int(like_count)

    playlist_signal = float(math.log1p(pc))
    playlist_boost = float(PLAYLIST_POPULARITY_ALPHA * playlist_signal)

    like_raw = lc
    cap = int(LIKE_CAP)
    effective_raw = min(like_raw, cap) if LIKE_CAP_ENABLED else like_raw
    like_signal = float(math.log1p(effective_raw))
    like_boost = float(LIKE_BOOST_ALPHA * like_signal)
    if pc > 0:
        like_boost = float(like_boost * float(LIKE_PLAYLIST_CORRELATION_DAMP))

    reorder_boost = float(REORDER_BOOST_ALPHA * rs)
    user_signal_score = float(reorder_boost)
    global_signal_score = float(playlist_boost + like_boost)
    signal_score = float(user_signal_score + global_signal_score)

    return {
        "user": {
            "reorder": {
                "signal": rs,
                "boost": reorder_boost,
            }
        },
        "global": {
            "playlist": {
                "raw": pc,
                "signal": playlist_signal,
                "boost": playlist_boost,
            },
            "likes": {
                "raw": like_raw,
                "signal": like_signal,
                "boost": like_boost,
            },
        },
        "total": {
            "user_signal_score": user_signal_score,
            "global_signal_score": global_signal_score,
            "signal_score": signal_score,
        },
    }
