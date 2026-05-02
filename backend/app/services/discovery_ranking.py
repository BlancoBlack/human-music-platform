"""
Discovery ranking: candidate universe (Step 2a) + scoring (Step 2b).

Scoring is CPU-only given preloaded maps (popularity, relevance, playlist counts, etc.).
``build_candidate_set`` batches DB reads including playlist membership counts.
``finalize_discovery_ranking`` may read playlists again when ``db`` is passed (curated rail).
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import random
from datetime import date, datetime, timezone

# Pipeline contract:
# build_candidate_set -> score_candidates -> finalize_discovery_ranking -> compose_discovery_sections
#
# All steps must operate on the SAME candidate universe.

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.models.global_listening_aggregate import GlobalListeningAggregate
from app.models.listening_aggregate import ListeningAggregate
from app.models.playlist import Playlist, PlaylistTrack
from app.models.release import Release
from app.models.song import Song
from app.models.song_media_asset import (
    SONG_MEDIA_KIND_MASTER_AUDIO,
    SongMediaAsset,
)
from app.services.discovery_candidate_pools import (
    _song_discoverable_sql,
    _utc_now_naive,
    get_discovery_visibility_stats,
    get_low_exposure_candidates,
    get_playlist_candidates,
    get_popular_candidates,
    get_user_candidates,
)

_MAX_CANDIDATES = 500
logger = logging.getLogger(__name__)

# Authenticated: blend relevance, discovery (1 − normalized pop), and popularity.
_WEIGHT_AUTH_REL = 0.45
_WEIGHT_AUTH_DISC = 0.35
_WEIGHT_AUTH_POP = 0.20

# Anonymous: no relevance signal — emphasize discovery vs popularity in-window.
_WEIGHT_ANON_DISC = 0.60
_WEIGHT_ANON_POP = 0.40

# Weak boost from playlist breadth: log1p(public playlist count per song). Not used in payouts.
_PLAYLIST_POPULARITY_ALPHA = 0.05

# When all candidates share the same global duration in-window, min–max is undefined.
_FLAT_POP_DISC = 0.5

# Fallback curated allowlist when ``finalize_discovery_ranking`` is called **without** ``db``.
# Production paths pass ``db`` and derive curated ids from public playlists instead.
DISCOVERY_CURATED_SONG_IDS: list[int] = []

_MAX_SECTION_PLAY_NOW = 10
_MAX_SECTION_FOR_YOU = 12
_MAX_SECTION_EXPLORE = 12
_MAX_SECTION_CURATED = 8
_EXPLORE_OFFSET_AFTER_FOR_YOU = 8
_MIN_EXPLORE_SCORE = 0.3
_LOW_EXPOSURE_CANDIDATE_MIN_SHARE = 0.30
_LOW_EXPOSURE_SECTION_MIN_SHARE = 0.25

DISCOVERY_SECTION_MICROCOPY: dict[str, str] = {
    "play_now": "Start here - zero friction",
    "for_you": "Based on your taste, with some exploration",
    "explore": "Step outside your usual patterns",
    "curated": "Selected by humans",
}


def load_global_popularity(db: Session, candidate_ids: list[int]) -> dict[int, float]:
    """
    Map each candidate ``song_id`` to ``GlobalListeningAggregate.total_duration``.

    Songs with no aggregate row are ``0.0`` (same economic memory as payouts).
    """
    if not candidate_ids:
        return {}

    rows = (
        db.query(GlobalListeningAggregate.song_id, GlobalListeningAggregate.total_duration)
        .filter(GlobalListeningAggregate.song_id.in_(candidate_ids))
        .all()
    )
    sparse: dict[int, float] = {}
    for sid, total in rows:
        if sid is None:
            continue
        sparse[int(sid)] = float(total or 0.0)

    return {int(cid): float(sparse.get(int(cid), 0.0)) for cid in candidate_ids}


def load_user_relevance(db: Session, user_id: int | None, candidate_ids: list[int]) -> dict[int, float]:
    """
    Map each candidate ``song_id`` to ``ListeningAggregate.total_duration`` for ``user_id``.

    Returns ``{}`` when ``user_id`` is None (anonymous). Caller can expand to zeros per candidate.
    """
    if user_id is None or not candidate_ids:
        return {}

    uid = int(user_id)
    rows = (
        db.query(ListeningAggregate.song_id, ListeningAggregate.total_duration)
        .filter(
            ListeningAggregate.user_id == uid,
            ListeningAggregate.song_id.in_(candidate_ids),
        )
        .all()
    )
    sparse: dict[int, float] = {}
    for sid, total in rows:
        if sid is None:
            continue
        sparse[int(sid)] = float(total or 0.0)

    return {int(cid): float(sparse.get(int(cid), 0.0)) for cid in candidate_ids}


def load_song_metadata(
    db: Session,
    candidate_ids: list[int],
) -> tuple[dict[int, int], dict[int, int]]:
    """Return ``song_id -> artist_id`` and ``song_id -> days_since_release`` maps."""
    if not candidate_ids:
        return {}, {}
    rows = (
        db.query(Song.id, Song.artist_id, Song.created_at)
        .filter(Song.id.in_(candidate_ids), Song.deleted_at.is_(None))
        .all()
    )
    now = datetime.utcnow()
    artist_by_song: dict[int, int] = {}
    days_since_release: dict[int, int] = {}
    for sid, artist_id, created_at in rows:
        i = int(sid)
        artist_by_song[i] = int(artist_id) if artist_id is not None else -i
        if created_at is None:
            days_since_release[i] = 365
        else:
            delta_days = (now - created_at).days
            days_since_release[i] = max(0, int(delta_days))
    return artist_by_song, days_since_release


def load_playlist_membership_counts(db: Session, candidate_ids: list[int]) -> dict[int, int]:
    """
    For each candidate song_id: number of **public**, non-deleted playlists that include it.

    One batched query (``GROUP BY song_id``). Songs absent from the result have count **0**.
    """
    if not candidate_ids:
        return {}
    rows = (
        db.query(PlaylistTrack.song_id, func.count(PlaylistTrack.playlist_id))
        .join(Playlist, Playlist.id == PlaylistTrack.playlist_id)
        .filter(
            Playlist.deleted_at.is_(None),
            Playlist.is_public.is_(True),
            PlaylistTrack.song_id.in_(candidate_ids),
        )
        .group_by(PlaylistTrack.song_id)
        .all()
    )
    return {int(sid): int(n) for sid, n in rows}


def load_user_listened_artists(db: Session, user_id: int | None) -> set[int]:
    """
    Return artist ids listened by user from ListeningAggregate (>0 duration), else empty.
    """
    if user_id is None:
        return set()
    rows = (
        db.query(Song.artist_id)
        .join(ListeningAggregate, ListeningAggregate.song_id == Song.id)
        .filter(
            ListeningAggregate.user_id == int(user_id),
            ListeningAggregate.total_duration > 0,
            Song.artist_id.isnot(None),
            Song.deleted_at.is_(None),
        )
        .distinct()
        .all()
    )
    return {int(r[0]) for r in rows if r[0] is not None}


def build_candidate_set(db: Session, user_id: int | None) -> dict:
    """
    Deterministic candidate list (≤500) plus aggregate maps for downstream scoring.

    Merge order: popular → user → playlist → low_exposure (after reserved low-exposure
    prefix); first occurrence wins; then cap.

    Returns:
        ``candidate_ids``: ordered list
        ``popularity``: ``song_id`` → global ``total_duration`` (0 if no row)
        ``relevance``: per-user ``ListeningAggregate.total_duration`` by ``song_id``.

    **Relevance contract:** Values may be sparse (missing keys imply zero listening).
    For anonymous users this is ``{}`` (no user-level aggregates). For logged-in users,
    keys may still be missing where the user has not listened. **Consumers must always
    use** ``relevance.get(song_id, 0)`` — never assume every ``candidate_id`` is present.
    """
    popular = get_popular_candidates(db)
    user_pool = get_user_candidates(db, user_id)
    playlist_pool = get_playlist_candidates(db, user_id)
    low_exposure = get_low_exposure_candidates(db)
    visibility_stats = get_discovery_visibility_stats(db)
    logger.info(
        "discovery_visibility_snapshot",
        extra={
            "user_id": int(user_id) if user_id is not None else None,
            **visibility_stats,
        },
    )

    popular_set = {int(x) for x in popular}
    user_set = {int(x) for x in user_pool}
    low_exposure_set = {int(x) for x in low_exposure}

    seen: set[int] = set()
    candidate_ids: list[int] = []
    candidate_pool_by_song: dict[int, str] = {}
    low_exposure_min = int(math.ceil(_MAX_CANDIDATES * _LOW_EXPOSURE_CANDIDATE_MIN_SHARE))

    # Reserve a floor of low-exposure candidates before broad merge/fill.
    for sid in low_exposure:
        i = int(sid)
        if i in seen:
            continue
        seen.add(i)
        candidate_ids.append(i)
        if len(candidate_ids) >= low_exposure_min or len(candidate_ids) >= _MAX_CANDIDATES:
            break

    # Label by first introducing stream (dedupe: skip if already seen — same as before).
    def _append_from_stream(stream_ids: list[int], pool_label: str) -> None:
        for sid in stream_ids:
            if len(candidate_ids) >= _MAX_CANDIDATES:
                return
            i = int(sid)
            if i in seen:
                continue
            seen.add(i)
            candidate_ids.append(i)
            candidate_pool_by_song[i] = pool_label

    _append_from_stream(popular, "popular")
    _append_from_stream(user_pool, "user")
    _append_from_stream(playlist_pool, "playlist")
    _append_from_stream(low_exposure, "low_exposure")

    # Assign pool labels for the reserved low-exposure prefix as well.
    for sid in candidate_ids:
        if sid in candidate_pool_by_song:
            continue
        if sid in low_exposure_set:
            candidate_pool_by_song[sid] = "low_exposure"
        elif sid in user_set:
            candidate_pool_by_song[sid] = "user"
        elif sid in popular_set:
            candidate_pool_by_song[sid] = "popular"
        else:
            candidate_pool_by_song[sid] = "unknown"

    popularity = load_global_popularity(db, candidate_ids)

    if user_id is None:
        # Empty: anonymous has no ListeningAggregate payload (see relevance contract above).
        relevance: dict[int, float] = {}
    else:
        relevance = load_user_relevance(db, user_id, candidate_ids)
    artist_by_song, days_since_release = load_song_metadata(db, candidate_ids)
    user_listened_artists = load_user_listened_artists(db, user_id)
    playlist_count_by_song = load_playlist_membership_counts(db, candidate_ids)

    return {
        "candidate_ids": candidate_ids,
        "low_exposure_reservoir": [int(sid) for sid in low_exposure],
        "popularity": popularity,
        "relevance": relevance,
        "artist_by_song": artist_by_song,
        "days_since_release": days_since_release,
        "user_listened_artists": user_listened_artists,
        "candidate_pool_by_song": candidate_pool_by_song,
        "playlist_count_by_song": playlist_count_by_song,
    }


def score_candidates(
    candidate_ids: list[int],
    popularity: dict[int, float],
    relevance: dict[int, float],
    artist_by_song: dict[int, int],
    days_since_release: dict[int, int],
    user_listened_artists: set[int],
    user_id: int | None,
    *,
    playlist_count_by_song: dict[int, int] | None = None,
) -> list[dict]:
    """
    Compute discovery score features per candidate (deterministic given inputs).

    Main ``score`` and ``for_you_score`` each gain the same small additive term
    ``+ _PLAYLIST_POPULARITY_ALPHA * log1p(playlist_count)`` (``playlist_count`` =
    public, non-deleted playlists containing the song; see ``load_playlist_membership_counts``).
    Boosting ``for_you_score`` keeps finalize ordering aligned with the composite ``score``.
    Omitted or missing ids imply count 0.

    Output order matches ``candidate_ids`` and includes section-specific scores:
    ``play_now_score``, ``for_you_score``, ``explore_score`` plus shared metadata
    (e.g. ``pop``, ``pop_log``, ``days_since_release``) used by selection.
    """
    # Prevents min/max errors on empty candidate set.
    if not candidate_ids:
        return []

    counts = playlist_count_by_song or {}

    # Anti-viral normalization: always use log(1 + popularity) wherever popularity is scored.
    pops_raw = [float(popularity.get(int(sid), 0.0)) for sid in candidate_ids]
    pops_log = [math.log1p(x) for x in pops_raw]
    p_min = min(pops_log)
    p_max = max(pops_log)
    flat_pop = p_max == p_min

    rels_raw = [float(relevance.get(int(sid), 0.0)) for sid in candidate_ids]
    r_max = max(rels_raw) if user_id is not None else 0.0

    sorted_pop = sorted(pops_log)
    p90_idx = max(0, int(math.ceil(0.9 * len(sorted_pop))) - 1)
    explore_pop_cutoff = sorted_pop[p90_idx]

    out: list[dict] = []
    for idx, sid in enumerate(candidate_ids):
        song_id = int(sid)
        rel_raw = rels_raw[idx]
        pop_raw = pops_raw[idx]
        pop_log = pops_log[idx]
        artist_id = int(artist_by_song.get(song_id, -song_id))
        days = int(days_since_release.get(song_id, 365))

        if user_id is None:
            rel_i = 0.0
        elif r_max > 0.0:
            rel_i = rel_raw / r_max
        else:
            rel_i = 0.0

        if flat_pop:
            pop_i = _FLAT_POP_DISC
            disc_i = _FLAT_POP_DISC
        else:
            pop_i = (pop_log - p_min) / (p_max - p_min)
            disc_i = 1.0 - pop_i

        recency_i = max(0.0, 1.0 - (min(days, 60) / 60.0))
        novelty_i = max(0.0, 1.0 - (min(days, 30) / 30.0))
        novelty_boost = 0.2 if days < 7 else 0.0
        rand_i = random.Random(song_id).uniform(0.0, 1.0)
        user_has_not_listened_to_artist = artist_id not in user_listened_artists
        exploration_boost = 1.0 if user_has_not_listened_to_artist else 0.0

        # Entry layer: momentum + freshness + jitter.
        play_now_score = 0.6 * pop_i + 0.2 * recency_i + 0.2 * rand_i + novelty_boost

        # Personalization: 70/30 behavior with explicit exploration pressure.
        for_you_score = 0.5 * rel_i + 0.2 * pop_i + 0.3 * exploration_boost + novelty_boost

        # Fair discovery: engagement + novelty + recency; exclude top 10% by popularity.
        early_engagement = pop_i
        explore_score = 0.5 * early_engagement + 0.3 * novelty_i + 0.2 * recency_i + novelty_boost
        explore_excluded = pop_log >= explore_pop_cutoff and len(candidate_ids) >= 10
        if explore_excluded:
            explore_score = -1.0

        if user_id is None:
            base_score = for_you_score if candidate_ids else (_WEIGHT_ANON_DISC * disc_i + _WEIGHT_ANON_POP * pop_i)
        else:
            base_score = for_you_score

        # Derived quality proxy (no new query path): higher when user relevance
        # keeps pace with global popularity for the same candidate.
        quality_score = (rel_raw + 1.0) / (pop_raw + 5.0)
        quality_penalty = max(
            0.55,
            min(1.0, 0.4 + (0.6 * quality_score)),
        )
        playlist_count = int(counts.get(song_id, 0))
        playlist_signal = math.log1p(playlist_count)
        playlist_boost = _PLAYLIST_POPULARITY_ALPHA * playlist_signal
        score = float(base_score) * float(quality_penalty) + playlist_boost

        out.append(
            {
                "song_id": song_id,
                "score": float(score),
                "play_now_score": float(play_now_score),
                "for_you_score": float(for_you_score) + playlist_boost,
                "explore_score": float(explore_score),
                "explore_excluded": bool(explore_excluded),
                "score_base": float(base_score),
                "quality_score": float(quality_score),
                "quality_penalty": float(quality_penalty),
                "rel": float(rel_i),
                "pop": float(pop_i),
                "pop_raw": float(pop_raw),
                "pop_log": float(pop_log),
                "disc": float(disc_i),
                "artist_id": artist_id,
                "recency": float(recency_i),
                "novelty": float(novelty_i),
                "days_since_release": int(days),
                "playlist_count": int(playlist_count),
                "playlist_signal": float(playlist_signal),
            }
        )

    return out


def _final_sort_key(r: dict) -> tuple[float, float, float, int]:
    """Ascending sort on this key == for_you_score DESC, rel DESC, pop_log ASC, song_id ASC."""
    return (
        -float(r.get("for_you_score", r["score"])),
        -float(r["rel"]),
        float(r.get("pop_log", 0.0)),
        int(r["song_id"]),
    )


def _curated_daily_shuffle_seed(utc_date: date) -> int:
    """Stable per UTC calendar day — used only for curated playlist shuffle."""
    return int.from_bytes(
        hashlib.sha256(utc_date.isoformat().encode("utf-8")).digest()[:8],
        "big",
    )


def build_curated_ids_from_public_playlists(
    db: Session,
    candidate_ids: list[int],
    *,
    utc_date: date | None = None,
) -> list[int]:
    """
    Curated rail: public playlists (``updated_at DESC``), max **2** playable tracks each,
    playlist track order preserved while flattening. Keeps only ids in ``candidate_ids``,
    dedupes by first occurrence in that flatten order, then **deterministic shuffle**
    seeded by UTC date ``YYYY-MM-DD``, finally capped at ``_MAX_SECTION_CURATED``.

    No writes. Stable for all requests on the same UTC day (same DB snapshot).
    """
    if utc_date is None:
        utc_date = datetime.now(timezone.utc).date()

    candidates = {int(c) for c in candidate_ids}
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

    flattened: list[int] = []
    seen_song: set[int] = set()
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
            .limit(2)
            .all()
        )
        for (song_id,) in rows:
            sid = int(song_id)
            if sid not in candidates or sid in seen_song:
                continue
            seen_song.add(sid)
            flattened.append(sid)

    rng = random.Random(_curated_daily_shuffle_seed(utc_date))
    shuffled = flattened[:]
    rng.shuffle(shuffled)
    return shuffled[:_MAX_SECTION_CURATED]


def _dedupe_scored_items(scored: list[dict]) -> list[dict]:
    """
    One row per ``song_id``: keep the row that sorts first under final ranking order.

    Deterministic when duplicate inputs exist for the same id.
    """
    best: dict[int, dict] = {}
    for row in scored:
        sid = int(row["song_id"])
        cur = best.get(sid)
        if cur is None or _final_sort_key(row) < _final_sort_key(cur):
            best[sid] = row
    return [best[k] for k in sorted(best.keys())]


def finalize_discovery_ranking(
    scored_items: list[dict],
    candidate_ids: list[int],
    artist_by_song: dict[int, int],
    *,
    db: Session | None = None,
    curated_ids: list[int] | None = None,
    curated_utc_date: date | None = None,
) -> dict:
    """
    Sort scored rows, apply curated picks, return id lists only.

    Sort keys: ``score`` DESC, ``rel`` DESC, ``pop_raw`` ASC, ``song_id`` ASC.

    Curated source:
    - If ``curated_ids`` is set, use it (tests / overrides).
    - Else if ``db`` is set, build from **public playlists** via
      ``build_curated_ids_from_public_playlists`` (daily seeded shuffle; see there).
    - Else fall back to ``DISCOVERY_CURATED_SONG_IDS`` (typically empty).

    Only ids present in ``candidate_ids`` are kept; duplicates dropped; at most
    ``_MAX_SECTION_CURATED`` ids returned. Algorithmic ranked list excludes curated ids.
    """
    if curated_ids is not None:
        allow = curated_ids
    elif db is not None:
        allow = build_curated_ids_from_public_playlists(
            db,
            candidate_ids,
            utc_date=curated_utc_date,
        )
    else:
        allow = DISCOVERY_CURATED_SONG_IDS
    candidates = {int(c) for c in candidate_ids}

    seen_curated: set[int] = set()
    curated_out: list[int] = []
    for cid in allow:
        i = int(cid)
        if i not in candidates or i in seen_curated:
            continue
        seen_curated.add(i)
        curated_out.append(i)

    # IMPORTANT:
    # curated_ids are capped here to ensure they are not removed from ranked
    # without being displayed in the curated section.
    curated_out = curated_out[:_MAX_SECTION_CURATED]

    merged = _dedupe_scored_items(scored_items)
    # Only rank songs that are in the candidate universe
    merged = [r for r in merged if int(r["song_id"]) in candidates]

    merged.sort(key=_final_sort_key)

    curated_set = set(curated_out)
    ranked: list[int] = []
    seen_ranked: set[int] = set()
    artist_counts: dict[int, int] = {}
    for r in merged:
        sid = int(r["song_id"])
        if sid in curated_set or sid in seen_ranked:
            continue
        aid = int(artist_by_song.get(sid, -sid))
        if artist_counts.get(aid, 0) >= 2:
            continue
        artist_counts[aid] = artist_counts.get(aid, 0) + 1
        seen_ranked.add(sid)
        ranked.append(sid)

    return {
        "ranked_candidate_ids": ranked,
        "curated_ids": curated_out,
    }


def compose_discovery_sections(
    ranked_candidate_ids: list[int],
    curated_ids: list[int],
    *,
    scored_items: list[dict],
    artist_by_song: dict[int, int],
    candidate_pool_by_song: dict[int, str] | None = None,
    low_exposure_reservoir: list[int] | None = None,
    user_id: int | None = None,
    recent_song_ids: set[int] | None = None,
) -> dict[str, list[int]]:
    """
    Compose home sections from ranked ids using structured + adaptive selection.

    - Curated ids win: they are removed from algorithmic sections.
    - Per-section artist caps are enforced during selection.
    - Selection uses soft score buckets and deterministic pattern/randomized rules.
    - Returns optional ``_context_by_song`` metadata for hydration.
    """
    score_by_song: dict[int, dict] = {int(r["song_id"]): r for r in scored_items}

    curated: list[int] = []
    seen_c: set[int] = set()
    curated_artist_counts: dict[int, int] = {}
    for cid in curated_ids:
        i = int(cid)
        if i in seen_c:
            continue
        aid = int(artist_by_song.get(i, -i))
        if curated_artist_counts.get(aid, 0) >= 2:
            continue
        curated_artist_counts[aid] = curated_artist_counts.get(aid, 0) + 1
        seen_c.add(i)
        curated.append(i)
    curated_set = set(curated)

    ranked: list[int] = []
    seen_r: set[int] = set()
    for rid in ranked_candidate_ids:
        i = int(rid)
        if i in curated_set or i in seen_r:
            continue
        seen_r.add(i)
        ranked.append(i)

    def _ordered_ids(ids: list[int], score_key: str) -> list[int]:
        return sorted(
            ids,
            key=lambda sid: (
                -float(score_by_song.get(sid, {}).get(score_key, -1.0)),
                int(sid),
            ),
        )

    def _split_soft_buckets(ids: list[int], score_key: str) -> tuple[list[int], list[int], list[int]]:
        if not ids:
            return [], [], []
        vals = [float(score_by_song.get(sid, {}).get(score_key, -1.0)) for sid in ids]
        v_min = min(vals)
        v_max = max(vals)
        high: list[int] = []
        mid: list[int] = []
        low: list[int] = []
        for sid, v in zip(ids, vals):
            if v_max > v_min:
                normalized = (v - v_min) / (v_max - v_min)
            else:
                normalized = 0.5
            if normalized >= 0.8:
                high.append(sid)
            elif normalized >= 0.5:
                mid.append(sid)
            else:
                low.append(sid)
        # Safety: if thresholds collapse, recover distribution from ordering.
        if not high and ids:
            high = ids[: max(1, int(math.ceil(len(ids) * 0.30)))]
        if not mid and len(ids) > len(high):
            start = len(high)
            mid = ids[start : start + max(1, int(math.ceil(len(ids) * 0.40)))]
        covered = set(high) | set(mid)
        low = [sid for sid in ids if sid not in covered]
        return high, mid, low

    def _fill_simple(
        ids: list[int],
        *,
        limit: int,
        per_artist_cap: int,
        selected: set[int],
        artist_counts: dict[int, int],
    ) -> list[int]:
        out: list[int] = []
        for sid in ids:
            if sid in selected:
                continue
            aid = int(artist_by_song.get(sid, -sid))
            if artist_counts.get(aid, 0) >= per_artist_cap:
                continue
            artist_counts[aid] = artist_counts.get(aid, 0) + 1
            selected.add(sid)
            out.append(sid)
            if len(out) >= limit:
                break
        return out

    recent = {int(x) for x in (recent_song_ids or set())}

    def _take_from_bucket(
        bucket: list[int],
        *,
        selected: set[int],
        artist_counts: dict[int, int],
        per_artist_cap: int,
        random_pick: bool = False,
        allow_recent: bool = False,
    ) -> int | None:
        candidates = [
            sid
            for sid in bucket
            if sid not in selected and (allow_recent or sid not in recent)
        ]
        if not candidates and not allow_recent:
            candidates = [sid for sid in bucket if sid not in selected]
        if random_pick and candidates:
            local_rng = random.Random(81173 + len(selected))
            sid = int(local_rng.choice(candidates))
            aid = int(artist_by_song.get(sid, -sid))
            if artist_counts.get(aid, 0) < per_artist_cap:
                artist_counts[aid] = artist_counts.get(aid, 0) + 1
                selected.add(sid)
                return sid
            # if random candidate violates cap, fall through to deterministic scan
        for sid in candidates:
            aid = int(artist_by_song.get(sid, -sid))
            if artist_counts.get(aid, 0) >= per_artist_cap:
                continue
            artist_counts[aid] = artist_counts.get(aid, 0) + 1
            selected.add(sid)
            return sid
        return None

    def _weighted_pick_top5_play_now(
        ids: list[int],
        *,
        selected: set[int],
        artist_counts: dict[int, int],
    ) -> int | None:
        candidates = [sid for sid in ids if sid not in selected][:5]
        if not candidates:
            return None
        weights: list[float] = []
        for sid in candidates:
            meta = score_by_song.get(sid, {})
            base = max(0.001, float(meta.get("play_now_score", 0.0)))
            days = int(meta.get("days_since_release", 365))
            freshness_boost = 1.25 if days < 14 else 1.0
            aid = int(artist_by_song.get(sid, -sid))
            artist_boost = 1.15 if artist_counts.get(aid, 0) == 0 else 1.0
            jitter = 1.0 + (random.Random(91013 + sid).uniform(-0.04, 0.04))
            weights.append(base * freshness_boost * artist_boost * jitter)
        rnd = random.Random(42017 + sum(candidates) + len(selected))
        ordered = rnd.choices(candidates, weights=weights, k=1)
        for sid in ordered + candidates:
            aid = int(artist_by_song.get(sid, -sid))
            if artist_counts.get(aid, 0) >= 1:
                continue
            artist_counts[aid] = artist_counts.get(aid, 0) + 1
            selected.add(sid)
            return sid
        return None

    selected_global: set[int] = set()

    # PLAY NOW: choose 1 from top-5 with weighted contextual selection,
    # then continue with controlled variety.
    play_source = _ordered_ids(ranked, "play_now_score")
    pn_high, pn_mid, pn_low = _split_soft_buckets(play_source, "play_now_score")
    play_now: list[int] = []
    pn_artist_counts: dict[int, int] = {}
    first_pick = _weighted_pick_top5_play_now(
        play_source,
        selected=selected_global,
        artist_counts=pn_artist_counts,
    )
    if first_pick is not None:
        play_now.append(first_pick)
    for bucket, random_pick in ((pn_mid, False), (pn_low or pn_mid or pn_high, True)):
        if len(play_now) >= _MAX_SECTION_PLAY_NOW:
            break
        picked = _take_from_bucket(
            bucket,
            selected=selected_global,
            artist_counts=pn_artist_counts,
            per_artist_cap=1,
            random_pick=random_pick,
        )
        if picked is not None:
            play_now.append(picked)
    if len(play_now) < _MAX_SECTION_PLAY_NOW:
        play_now.extend(
            _fill_simple(
                play_source,
                limit=_MAX_SECTION_PLAY_NOW - len(play_now),
                per_artist_cap=1,
                selected=selected_global,
                artist_counts=pn_artist_counts,
            )
        )
    if not play_now and play_source:
        play_now.extend(
            _fill_simple(
                play_source,
                limit=min(_MAX_SECTION_PLAY_NOW, len(play_source)),
                per_artist_cap=1,
                selected=selected_global,
                artist_counts=pn_artist_counts,
            )
        )

    # FOR YOU: high/mid/low buckets with F,F,E,F,E,F pattern (F=high, E=mid).
    fy_source = [sid for sid in _ordered_ids(ranked, "for_you_score") if sid not in selected_global]
    fy_high, fy_mid, fy_low = _split_soft_buckets(fy_source, "for_you_score")
    for_you: list[int] = []
    fy_artist_counts: dict[int, int] = {}
    if not fy_high and not fy_mid:
        # Safety fallback when buckets are empty.
        for_you.extend(
            _fill_simple(
                fy_source,
                limit=_MAX_SECTION_FOR_YOU,
                per_artist_cap=2,
                selected=selected_global,
                artist_counts=fy_artist_counts,
            )
        )
    else:
        patterns = [
            ("F", "F", "E", "F", "E", "F"),
            ("F", "E", "F", "F", "E", "F"),
            ("F", "F", "E", "E", "F", "F"),
        ]
        uid = int(user_id) if user_id is not None else 0
        pattern = patterns[uid % len(patterns)]
        cursor = 0
        while len(for_you) < _MAX_SECTION_FOR_YOU:
            token = pattern[cursor % len(pattern)]
            cursor += 1
            bucket = fy_high if token == "F" else fy_mid
            picked = _take_from_bucket(
                bucket,
                selected=selected_global,
                artist_counts=fy_artist_counts,
                per_artist_cap=2,
            )
            if picked is not None:
                for_you.append(picked)
                continue
            # Fallback if target bucket is exhausted.
            fallback_bucket = fy_mid if token == "F" else fy_high
            picked = _take_from_bucket(
                fallback_bucket,
                selected=selected_global,
                artist_counts=fy_artist_counts,
                per_artist_cap=2,
            )
            if picked is not None:
                for_you.append(picked)
                continue
            if len(for_you) < _MAX_SECTION_FOR_YOU:
                fill = _fill_simple(
                    fy_high + fy_mid + fy_low,
                    limit=1,
                    per_artist_cap=2,
                    selected=selected_global,
                    artist_counts=fy_artist_counts,
                )
                if not fill:
                    break
                for_you.extend(fill)
    if not for_you and fy_source:
        for_you.extend(
            _fill_simple(
                fy_source,
                limit=min(_MAX_SECTION_FOR_YOU, len(fy_source)),
                per_artist_cap=2,
                selected=selected_global,
                artist_counts=fy_artist_counts,
            )
        )

    # EXPLORE: mid-first, inject low with guardrails, exclude top 10% flagged songs.
    explore_seed = [
        sid
        for sid in _ordered_ids(ranked, "explore_score")
        if sid not in selected_global
        and not bool(score_by_song.get(sid, {}).get("explore_excluded", False))
    ]
    ex_high, ex_mid, ex_low = _split_soft_buckets(explore_seed, "explore_score")
    explore: list[int] = []
    ex_artist_counts: dict[int, int] = {}
    mid_target = int(math.ceil(_MAX_SECTION_EXPLORE * 0.5))
    low_max = int(math.floor(_MAX_SECTION_EXPLORE * 0.2))
    mid_count = 0
    low_count = 0
    if not ex_mid and not ex_high:
        explore.extend(
            _fill_simple(
                explore_seed,
                limit=_MAX_SECTION_EXPLORE,
                per_artist_cap=2,
                selected=selected_global,
                artist_counts=ex_artist_counts,
            )
        )
    else:
        idx = 0
        while len(explore) < _MAX_SECTION_EXPLORE:
            idx += 1
            if idx % 3 == 0 and ex_low and low_count < low_max:
                low_candidates = [
                    sid
                    for sid in ex_low
                    if float(score_by_song.get(sid, {}).get("explore_score", -1.0)) >= _MIN_EXPLORE_SCORE
                ]
                picked = _take_from_bucket(
                    low_candidates,
                    selected=selected_global,
                    artist_counts=ex_artist_counts,
                    per_artist_cap=2,
                    random_pick=True,
                )
                if picked is not None:
                    explore.append(picked)
                    low_count += 1
                    continue
            picked = None
            if mid_count < mid_target:
                picked = _take_from_bucket(
                    ex_mid,
                    selected=selected_global,
                    artist_counts=ex_artist_counts,
                    per_artist_cap=2,
                )
                if picked is not None:
                    mid_count += 1
            if picked is None:
                picked = _take_from_bucket(
                    ex_high,
                    selected=selected_global,
                    artist_counts=ex_artist_counts,
                    per_artist_cap=2,
                )
            if picked is None:
                picked = _take_from_bucket(
                    ex_mid,
                    selected=selected_global,
                    artist_counts=ex_artist_counts,
                    per_artist_cap=2,
                )
                if picked is not None:
                    mid_count += 1
            if picked is None:
                fill = _fill_simple(
                    ex_mid + ex_high + ex_low,
                    limit=1,
                    per_artist_cap=2,
                    selected=selected_global,
                    artist_counts=ex_artist_counts,
                )
                if not fill:
                    break
                explore.extend(fill)
                if fill and fill[0] in ex_mid:
                    mid_count += 1
                if fill and fill[0] in ex_low:
                    low_count += 1
            else:
                explore.append(picked)
    if not explore and explore_seed:
        explore.extend(
            _fill_simple(
                explore_seed,
                limit=min(_MAX_SECTION_EXPLORE, len(explore_seed)),
                per_artist_cap=2,
                selected=selected_global,
                artist_counts=ex_artist_counts,
            )
        )

    # FINAL STEP: enforce minimum low-exposure share per section after all caps/filters.
    pool_map = candidate_pool_by_song or {}
    low_ranked = [sid for sid in ranked if pool_map.get(int(sid)) == "low_exposure"]
    reservoir_unique: list[int] = []
    seen_reservoir: set[int] = set()
    for sid in (low_exposure_reservoir or []):
        i = int(sid)
        if i in seen_reservoir:
            continue
        seen_reservoir.add(i)
        reservoir_unique.append(i)

    used_initial = set(play_now) | set(for_you) | set(explore) | set(curated)

    def _is_dev_env() -> bool:
        return os.getenv("APP_ENV", "").strip().lower() in {"dev", "development", "local"}

    def _enforce_low_exposure_section(section_name: str, section: list[int]) -> list[int]:
        if not section:
            return section
        target = int(math.ceil(len(section) * _LOW_EXPOSURE_SECTION_MIN_SHARE))
        before = sum(1 for sid in section if pool_map.get(int(sid)) == "low_exposure")
        deficit = max(0, target - before)
        if deficit <= 0:
            if _is_dev_env():
                logger.info(
                    "low_exposure_enforcement",
                    extra={
                        "low_exposure_enforcement": {
                            "section": section_name,
                            "before": int(before),
                            "after": int(before),
                            "target": int(target),
                        }
                    },
                )
            return section

        # Highest-ranked low-exposure first; fallback to external reservoir for strict guarantee.
        preferred_ranked = [sid for sid in low_ranked if sid not in used_initial and sid not in section]
        fallback_ranked_reuse = [sid for sid in low_ranked if sid not in section]
        preferred_reservoir = [sid for sid in reservoir_unique if sid not in used_initial and sid not in section]
        fallback_reservoir_reuse = [sid for sid in reservoir_unique if sid not in section]
        replacement_pool = (
            preferred_ranked
            + [sid for sid in fallback_ranked_reuse if sid not in preferred_ranked]
            + [sid for sid in preferred_reservoir if sid not in preferred_ranked and sid not in fallback_ranked_reuse]
            + [
                sid
                for sid in fallback_reservoir_reuse
                if sid not in preferred_ranked
                and sid not in fallback_ranked_reuse
                and sid not in preferred_reservoir
            ]
        )
        if not replacement_pool:
            replacement_pool = low_ranked + [sid for sid in reservoir_unique if sid not in low_ranked]

        # Replace lowest-ranked non-low-exposure items (tail) first.
        replacement_idx = 0
        added_from_reservoir = 0
        for idx in range(len(section) - 1, -1, -1):
            if deficit <= 0 or replacement_idx >= len(replacement_pool):
                break
            if pool_map.get(int(section[idx])) == "low_exposure":
                continue
            chosen = int(replacement_pool[replacement_idx])
            if chosen in reservoir_unique and chosen not in low_ranked:
                added_from_reservoir += 1
            section[idx] = chosen
            used_initial.add(chosen)
            replacement_idx += 1
            deficit -= 1

        after = sum(1 for sid in section if pool_map.get(int(sid)) == "low_exposure")
        if _is_dev_env():
            logger.info(
                "low_exposure_enforcement",
                extra={
                    "low_exposure_enforcement": {
                        "section": section_name,
                        "required": int(target),
                        "before": int(before),
                        "after": int(after),
                        "target": int(target),
                        "added_from_reservoir": int(added_from_reservoir),
                    }
                },
            )
        return section

    play_now = _enforce_low_exposure_section("play_now", play_now)
    for_you = _enforce_low_exposure_section("for_you", for_you)
    explore = _enforce_low_exposure_section("explore", explore)

    context_by_song: dict[int, str | None] = {}
    for sid in set(play_now + for_you + explore + curated):
        meta = score_by_song.get(int(sid), {})
        days = int(meta.get("days_since_release", 365))
        pop_norm = float(meta.get("pop", 0.0))
        if days <= 7:
            context_by_song[int(sid)] = "Fresh this week"
        elif pop_norm >= 0.8:
            context_by_song[int(sid)] = "Trending now"
        elif pop_norm <= 0.3:
            context_by_song[int(sid)] = "Hidden gem"
        else:
            context_by_song[int(sid)] = None

    return {
        "play_now": play_now,
        "for_you": for_you,
        "explore": explore,
        "curated": curated,
        "_context_by_song": context_by_song,  # optional transport for hydration layer
    }
