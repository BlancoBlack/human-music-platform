"""Read-only aggregates for admin discovery signal visibility (no new tables)."""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import desc, func, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.sql import case as sql_case

from app.models.artist import Artist
from app.models.discovery_event import DiscoveryEvent
from app.models.like_event import LikeEvent
from app.models.playlist import Playlist
from app.models.playlist_reorder_event import PlaylistReorderEvent
from app.models.song import Song
from app.services.reorder_signal_service import (
    _REORDER_SIGNAL_WINDOW_DAYS,
    _liked_playlist_match,
    _weighted_delta_column,
)
from app.services.signal_aggregator import (
    LIKE_CAP,
    LIKE_CAP_ENABLED,
    LIKE_MATURITY_MINUTES,
    LIKE_PLAYLIST_CORRELATION_DAMP,
    compute_signal_contributions,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

_HISTOGRAM_BUCKETS_ORDER = ("0", "0-2", "2-5", "5-10", "10-20", "20+")

_LIKE_SIGNAL_HIST_LABELS = (
    "0.0-0.5",
    "0.5-1.0",
    "1.0-1.5",
    "1.5-2.0",
    "2.0-2.5",
    "2.5-3.0",
    "3.0-3.5",
    "3.5-4.0",
    ">4.0",
)
_LIKE_BOOST_HIST_LABELS = (
    "0.0-0.008",
    "0.008-0.016",
    "0.016-0.024",
    "0.024-0.032",
    "0.032-0.040",
    "0.040-0.048",
    ">0.048",
)


def _empty_like_signal_histogram() -> list[dict[str, int | str]]:
    return [{"bucket": b, "song_count": 0} for b in _LIKE_SIGNAL_HIST_LABELS]


def _empty_like_boost_histogram() -> list[dict[str, int | str]]:
    return [{"bucket": b, "song_count": 0} for b in _LIKE_BOOST_HIST_LABELS]


def _like_signal_hist_key(s: float) -> str:
    if s > 4.0:
        return ">4.0"
    i = min(int(s // 0.5), 7)
    return _LIKE_SIGNAL_HIST_LABELS[i]


def _like_boost_hist_key(b: float) -> str:
    if b > 0.048:
        return ">0.048"
    i = min(int(b // 0.008), 5)
    return _LIKE_BOOST_HIST_LABELS[i]


def _baseline_likes_ranking_context() -> dict:
    return {
        "maturity_minutes": int(LIKE_MATURITY_MINUTES),
        "like_cap": int(LIKE_CAP),
        "like_cap_enabled": bool(LIKE_CAP_ENABLED),
        "playlist_like_correlation_damp": float(LIKE_PLAYLIST_CORRELATION_DAMP),
        "sample_songs": 0,
        "like_signal_histogram": _empty_like_signal_histogram(),
        "like_boost_histogram": _empty_like_boost_histogram(),
        "correlation": {
            "avg_like_signal": 0.0,
            "avg_playlist_signal": 0.0,
            "pct_songs_with_like_and_playlist": 0.0,
        },
        "avg_contributions": {
            "playlist_boost": 0.0,
            "like_boost": 0.0,
            "reorder_boost": None,
            "reorder_note": "Per-user; not aggregated in this global sample",
        },
    }


def _build_likes_ranking_context(db: "Session", cutoff: datetime, mature_upper: datetime) -> dict:
    """
    Admin-only: distribution + correlation stats for **ranking** like signal (matured 14d).

    Uses up to 2000 songs with the most matured likes in-window; one playlist-membership
    batch query; per-song ``compute_signal_contributions`` (reorder=0) for histograms.
    """
    from app.services.discovery_ranking import load_playlist_membership_counts

    cnt = func.count(LikeEvent.id)
    rows = (
        db.query(LikeEvent.song_id, cnt.label("raw_cnt"))
        .filter(
            LikeEvent.created_at >= cutoff,
            LikeEvent.created_at <= mature_upper,
        )
        .group_by(LikeEvent.song_id)
        .order_by(desc(cnt))
        .limit(2000)
        .all()
    )
    if not rows:
        return _baseline_likes_ranking_context()

    song_ids = [int(sid) for sid, _ in rows if sid is not None]
    raw_by_song = {int(sid): int(c or 0) for sid, c in rows if sid is not None}
    playlist_by_song = load_playlist_membership_counts(db, song_ids)

    sig_hist: dict[str, int] = {str(b): 0 for b in _LIKE_SIGNAL_HIST_LABELS}
    boost_hist: dict[str, int] = {str(b): 0 for b in _LIKE_BOOST_HIST_LABELS}
    like_sigs: list[float] = []
    pl_sigs: list[float] = []
    pl_boosts: list[float] = []
    lk_boosts: list[float] = []
    n_both = 0

    for sid in song_ids:
        raw = int(raw_by_song.get(sid, 0))
        pc = int(playlist_by_song.get(sid, 0))
        sig = compute_signal_contributions(pc, 0.0, like_count=raw)
        ls = float(sig["global"]["likes"]["signal"])
        lb = float(sig["global"]["likes"]["boost"])
        ps = float(sig["global"]["playlist"]["signal"])
        pb = float(sig["global"]["playlist"]["boost"])
        like_sigs.append(ls)
        pl_sigs.append(ps)
        pl_boosts.append(pb)
        lk_boosts.append(lb)
        sl = _like_signal_hist_key(ls)
        bl = _like_boost_hist_key(lb)
        sig_hist[sl] += 1
        boost_hist[bl] += 1
        if raw > 0 and pc > 0:
            n_both += 1

    n = len(song_ids)
    avg_ls = sum(like_sigs) / float(n) if n else 0.0
    avg_ps = sum(pl_sigs) / float(n) if n else 0.0
    pct_both = (n_both / float(n)) if n else 0.0
    avg_pb = sum(pl_boosts) / float(n) if n else 0.0
    avg_lb = sum(lk_boosts) / float(n) if n else 0.0

    return {
        "maturity_minutes": int(LIKE_MATURITY_MINUTES),
        "like_cap": int(LIKE_CAP),
        "like_cap_enabled": bool(LIKE_CAP_ENABLED),
        "playlist_like_correlation_damp": float(LIKE_PLAYLIST_CORRELATION_DAMP),
        "sample_songs": n,
        "like_signal_histogram": [
            {"bucket": b, "song_count": int(sig_hist[b])} for b in _LIKE_SIGNAL_HIST_LABELS
        ],
        "like_boost_histogram": [
            {"bucket": b, "song_count": int(boost_hist[b])} for b in _LIKE_BOOST_HIST_LABELS
        ],
        "correlation": {
            "avg_like_signal": round(avg_ls, 6),
            "avg_playlist_signal": round(avg_ps, 6),
            "pct_songs_with_like_and_playlist": round(pct_both, 6),
        },
        "avg_contributions": {
            "playlist_boost": round(avg_pb, 6),
            "like_boost": round(avg_lb, 6),
            "reorder_boost": None,
            "reorder_note": "Per-user; not aggregated in this global sample",
        },
    }


def _bucket_per_song_weighted_sum(s: float) -> str:
    if s <= 0:
        return "0"
    if s <= 2:
        return "0-2"
    if s <= 5:
        return "2-5"
    if s <= 10:
        return "5-10"
    if s <= 20:
        return "10-20"
    return "20+"


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = max(0, int(math.ceil(0.95 * len(s))) - 1)
    return float(s[idx])


def batch_song_artist_labels(db: "Session", song_ids: list[int]) -> dict[int, tuple[str, str]]:
    """``song_id`` → ``(title, artist_name)``. Missing songs omitted (caller may default)."""
    ids = sorted({int(x) for x in song_ids if x is not None})
    if not ids:
        return {}
    rows = (
        db.query(Song.id, Song.title, Artist.name)
        .outerjoin(Artist, Artist.id == Song.artist_id)
        .filter(Song.id.in_(ids))
        .all()
    )
    out: dict[int, tuple[str, str]] = {}
    for sid, title, aname in rows:
        if sid is None:
            continue
        t = str(title or "").strip() or "—"
        a = str(aname).strip() if aname is not None else "—"
        out[int(sid)] = (t, a or "—")
    return out


def _empty_signal_snapshot() -> dict:
    hist = [{"bucket": b, "song_count": 0} for b in _HISTOGRAM_BUCKETS_ORDER]
    scale = {"avg_weighted_sum": 0.0, "p95_weighted_sum": 0.0}
    return {
        "reorder": {
            "window_days": _REORDER_SIGNAL_WINDOW_DAYS,
            "overview": {"row_count": 0, "distinct_users": 0, "distinct_songs": 0},
            "scale": scale,
            "liked_share_of_weighted_sum": 0.0,
            "per_song_weighted_histogram": hist,
            "top_reorder_songs": [],
        },
        "likes": {
            "window_days": _REORDER_SIGNAL_WINDOW_DAYS,
            "overview": {"total_events": 0, "distinct_users": 0, "distinct_songs": 0},
            "top_liked_songs": [],
            "ranking_context": _baseline_likes_ranking_context(),
        },
        "top_reorder_coverage_in_discovery": 0.0,
        "likes_reorder_overlap": 0.0,
    }


def build_admin_signal_snapshot(db: "Session") -> dict:
    """
    Aggregate reorder + like signals for ``GET /discovery/admin/analytics``.

    Reorder rules match ``load_reorder_signal_by_song`` (14d, join playlists, clamp,
    liked downweight). Coverage uses **distinct** ``song_id`` in 24h impressions vs
    those also in top-50 reorder set (not row-inflated). ``likes_reorder_overlap`` =
    |top50_reorder ∩ top50_likes| / |top50_reorder| (0 if no reorder top set).
    """
    out = _empty_signal_snapshot()
    cutoff = datetime.utcnow() - timedelta(days=_REORDER_SIGNAL_WINDOW_DAYS)
    mature_upper = datetime.utcnow() - timedelta(minutes=int(LIKE_MATURITY_MINUTES))
    cutoff_24h = datetime.utcnow() - timedelta(days=1)

    top_reorder_ids: set[int] = set()
    top_liked_ids: list[int] = []

    reorder_ok = True
    try:
        db.execute(text("SELECT 1 FROM playlist_reorder_events LIMIT 1"))
    except OperationalError:
        reorder_ok = False

    if reorder_ok:
        weighted = _weighted_delta_column()
        join_filters = (
            PlaylistReorderEvent.created_at >= cutoff,
            PlaylistReorderEvent.delta_position > 0,
            Playlist.deleted_at.is_(None),
            Playlist.owner_user_id == PlaylistReorderEvent.user_id,
        )
        cnt_row = (
            db.query(
                func.count(PlaylistReorderEvent.id),
                func.count(func.distinct(PlaylistReorderEvent.user_id)),
                func.count(func.distinct(PlaylistReorderEvent.song_id)),
            )
            .select_from(PlaylistReorderEvent)
            .join(Playlist, Playlist.id == PlaylistReorderEvent.playlist_id)
            .filter(*join_filters)
            .one()
        )
        row_count = int(cnt_row[0] or 0)
        distinct_users = int(cnt_row[1] or 0)
        distinct_songs = int(cnt_row[2] or 0)

        liked_sum_expr = func.sum(sql_case((_liked_playlist_match(), weighted), else_=0))
        total_sum_expr = func.sum(weighted)
        sums_row = (
            db.query(liked_sum_expr, total_sum_expr)
            .select_from(PlaylistReorderEvent)
            .join(Playlist, Playlist.id == PlaylistReorderEvent.playlist_id)
            .filter(*join_filters)
            .one()
        )
        liked_w = float(sums_row[0] or 0.0)
        total_w = float(sums_row[1] or 0.0)
        liked_share = liked_w / total_w if total_w > 0.0 else 0.0

        per_song_rows = (
            db.query(
                PlaylistReorderEvent.song_id,
                func.sum(weighted).label("wsum"),
                func.count(PlaylistReorderEvent.id).label("ecnt"),
            )
            .select_from(PlaylistReorderEvent)
            .join(Playlist, Playlist.id == PlaylistReorderEvent.playlist_id)
            .filter(*join_filters)
            .group_by(PlaylistReorderEvent.song_id)
            .all()
        )
        per_song_sums: list[float] = []
        top_list: list[dict] = []
        for sid, wsum, ecnt in per_song_rows:
            if sid is None:
                continue
            w = float(wsum or 0.0)
            per_song_sums.append(w)
            top_list.append(
                {
                    "song_id": int(sid),
                    "weighted_sum": round(w, 4),
                    "event_count": int(ecnt or 0),
                }
            )
        top_list.sort(key=lambda r: r["weighted_sum"], reverse=True)
        top_list = top_list[:50]
        top_reorder_ids = {int(r["song_id"]) for r in top_list}

        n_songs = len(per_song_sums)
        avg_w = sum(per_song_sums) / float(n_songs) if n_songs else 0.0
        p95_w = _p95(per_song_sums)

        labels = batch_song_artist_labels(db, [r["song_id"] for r in top_list])
        for r in top_list:
            sid = int(r["song_id"])
            title, artist = labels.get(sid, ("—", "—"))
            r["title"] = title
            r["artist_name"] = artist

        hist_counts: dict[str, int] = {b: 0 for b in _HISTOGRAM_BUCKETS_ORDER}
        for w in per_song_sums:
            hist_counts[_bucket_per_song_weighted_sum(w)] += 1
        histogram = [{"bucket": b, "song_count": hist_counts[b]} for b in _HISTOGRAM_BUCKETS_ORDER]

        out["reorder"] = {
            "window_days": _REORDER_SIGNAL_WINDOW_DAYS,
            "overview": {
                "row_count": row_count,
                "distinct_users": distinct_users,
                "distinct_songs": distinct_songs,
            },
            "scale": {
                "avg_weighted_sum": round(avg_w, 6),
                "p95_weighted_sum": round(p95_w, 6),
            },
            "liked_share_of_weighted_sum": round(liked_share, 6),
            "per_song_weighted_histogram": histogram,
            "top_reorder_songs": top_list,
        }

        coverage = 0.0
        try:
            denom = int(
                db.query(func.count(func.distinct(DiscoveryEvent.song_id)))
                .filter(
                    DiscoveryEvent.event_type == "impression",
                    DiscoveryEvent.created_at >= cutoff_24h,
                    DiscoveryEvent.song_id.isnot(None),
                )
                .scalar()
                or 0
            )
            if denom > 0 and top_reorder_ids:
                num = int(
                    db.query(func.count(func.distinct(DiscoveryEvent.song_id)))
                    .filter(
                        DiscoveryEvent.event_type == "impression",
                        DiscoveryEvent.created_at >= cutoff_24h,
                        DiscoveryEvent.song_id.isnot(None),
                        DiscoveryEvent.song_id.in_(list(top_reorder_ids)),
                    )
                    .scalar()
                    or 0
                )
                coverage = num / float(denom)
        except OperationalError:
            coverage = 0.0
        out["top_reorder_coverage_in_discovery"] = round(coverage, 6)

    likes_ok = True
    try:
        db.execute(text("SELECT 1 FROM like_events LIMIT 1"))
    except OperationalError:
        likes_ok = False

    if likes_ok:
        like_time = (
            LikeEvent.created_at >= cutoff,
            LikeEvent.created_at <= mature_upper,
        )
        like_total = int(
            db.query(func.count(LikeEvent.id)).filter(*like_time).scalar() or 0
        )
        like_distinct_users = int(
            db.query(func.count(func.distinct(LikeEvent.user_id)))
            .filter(*like_time)
            .scalar()
            or 0
        )
        like_distinct_songs = int(
            db.query(func.count(func.distinct(LikeEvent.song_id)))
            .filter(*like_time)
            .scalar()
            or 0
        )
        top_liked = (
            db.query(LikeEvent.song_id, func.count(LikeEvent.id).label("cnt"))
            .filter(*like_time)
            .group_by(LikeEvent.song_id)
            .order_by(func.count(LikeEvent.id).desc())
            .limit(50)
            .all()
        )
        liked_rows = [
            {"song_id": int(sid), "count": int(c or 0)}
            for sid, c in top_liked
            if sid is not None
        ]
        top_liked_ids = [r["song_id"] for r in liked_rows]
        labels_l = batch_song_artist_labels(db, top_liked_ids)
        for r in liked_rows:
            sid = int(r["song_id"])
            title, artist = labels_l.get(sid, ("—", "—"))
            r["title"] = title
            r["artist_name"] = artist
            r["artist"] = artist

        out["likes"] = {
            "window_days": _REORDER_SIGNAL_WINDOW_DAYS,
            "overview": {
                "total_events": like_total,
                "distinct_users": like_distinct_users,
                "distinct_songs": like_distinct_songs,
            },
            "top_liked_songs": liked_rows,
            "ranking_context": _build_likes_ranking_context(db, cutoff, mature_upper),
        }

    if top_reorder_ids:
        liked_set = set(top_liked_ids)
        overlap = len(top_reorder_ids & liked_set) / float(len(top_reorder_ids))
        out["likes_reorder_overlap"] = round(overlap, 6)
    return out
