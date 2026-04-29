"""
Discovery API: ranked home sections with hydrated track rows.
"""

from __future__ import annotations

import logging
import os
import random
import time
from uuid import uuid4
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_optional_user
from app.core.database import get_db
from app.models.discovery_event import DiscoveryEvent
from app.models.song import Song
from app.models.user_profile import UserProfile
from app.models.user import User
from app.services.onboarding_state_service import (
    COMPLETED,
    DISCOVERY_STARTED,
    PREFERENCES_SET,
    advance_onboarding_state,
    validate_onboarding_state,
)
from app.services.discovery_hydration import build_discovery_home_sections
from app.services.discovery_ranking import (
    DISCOVERY_SECTION_MICROCOPY,
    build_candidate_set,
    compose_discovery_sections,
    finalize_discovery_ranking,
    score_candidates,
)

router = APIRouter()
logger = logging.getLogger(__name__)
_SECTION_KEYS = ("play_now", "for_you", "explore", "curated")
_RANKING_VERSION = "v1"


def _parse_sample_rate(raw: str | None) -> float:
    try:
        value = float(str(raw or "1.0").strip())
    except (TypeError, ValueError):
        return 1.0
    return max(0.0, min(1.0, value))


_DISCOVERY_IMPRESSION_SAMPLE_RATE = _parse_sample_rate(
    os.getenv("DISCOVERY_IMPRESSION_SAMPLE_RATE")
)


def _is_development_env() -> bool:
    env = (os.getenv("APP_ENV") or os.getenv("ENV") or "").strip().lower()
    return env in {"dev", "development"}


class DiscoveryPlayEventIn(BaseModel):
    event_type: str
    request_id: str
    song_id: int | None = None
    section: str | None = None
    position: int | None = None
    auth_state: str | None = None
    allowed_to_play: bool | None = None
    blocked_reason: str | None = None
    ranking_version: str | None = None


def _float_ratio(numerator: int | float, denominator: int | float) -> float:
    den = float(denominator)
    if den <= 0.0:
        return 0.0
    return round(float(numerator) / den, 6)


def _insert_discovery_impressions(
    db: Session,
    *,
    request_id: str,
    uid: int | None,
    section_ids: dict[str, list[int]],
    scored: list[dict],
    artist_by_song: dict[int, int],
    candidate_pool_by_song: dict[int, str],
) -> int:
    score_by_song = {int(r["song_id"]): r for r in scored}
    rows: list[DiscoveryEvent] = []
    global_pos = 0
    for section in _SECTION_KEYS:
        ids = section_ids.get(section) or []
        for idx, sid_raw in enumerate(ids):
            current_global_pos = global_pos
            global_pos += 1
            sid = int(sid_raw)
            score_row = score_by_song.get(sid, {})
            artist_id = int(
                score_row.get(
                    "artist_id",
                    artist_by_song.get(sid, -sid),
                )
            )
            metadata_json = {
                "ranking_version": _RANKING_VERSION,
                "section_position_global": int(current_global_pos),
                "score_play_now": float(score_row.get("play_now_score", 0.0)),
                "score_for_you": float(score_row.get("for_you_score", 0.0)),
                "score_explore": float(score_row.get("explore_score", 0.0)),
                "candidate_pool": (
                    "curated"
                    if section == "curated"
                    else str(candidate_pool_by_song.get(sid, "unknown"))
                ),
                "explore_excluded": bool(score_row.get("explore_excluded", False)),
                "scores": {
                    "play_now": float(score_row.get("play_now_score", 0.0)),
                    "for_you": float(score_row.get("for_you_score", 0.0)),
                    "explore": float(score_row.get("explore_score", 0.0)),
                }
            }
            rows.append(
                DiscoveryEvent(
                    event_type="impression",
                    request_id=request_id,
                    user_id=uid,
                    song_id=sid,
                    artist_id=artist_id,
                    section=section,
                    position=int(idx),
                    metadata_json=metadata_json,
                )
            )
    if rows:
        db.add_all(rows)
    return len(rows)


def _empty_admin_analytics_payload() -> dict:
    return {
        "ctr_by_section": [],
        "ctr_by_position": [],
        "candidate_pool_performance": [],
        "candidate_pool_by_section": [],
        "ctr_by_ranking_version": [],
        "top_artists_concentration": {
            "top_artists": [],
            "top_artists_share": 0.0,
            "total_impressions": 0,
        },
        "high_score_low_ctr_anomalies": [],
        "diversity_per_request": {
            "avg_unique_artists": 0.0,
            "min_unique_artists": 0,
            "max_unique_artists": 0,
        },
        "score_ctr_correlation": [],
        "quality_by_section": [],
        "quality_by_candidate_pool": [],
        "quality_by_score_bucket": [],
        "listen_per_impression_by_section": [],
        "listen_per_impression_by_candidate_pool": [],
        "listen_per_impression_by_score_bucket": [],
        "valid_listen_per_click_by_section": [],
    }


@router.get("/home")
def get_discovery_home(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User | None, Depends(get_optional_user)],
):
    """
    Discovery home: candidate pools → score → finalize → sections → hydrated rows.

    Response keys: ``play_now``, ``for_you``, ``explore``, ``curated`` (each a list of
    track objects with strict JSON types).
    """
    uid = int(user.id) if user is not None else None
    anonymous = user is None

    request_id = str(uuid4())

    t0 = time.perf_counter()
    payload = build_candidate_set(db, uid)
    pool_ms = (time.perf_counter() - t0) * 1000.0

    t1 = time.perf_counter()
    scored = score_candidates(
        payload["candidate_ids"],
        payload["popularity"],
        payload["relevance"],
        payload["artist_by_song"],
        payload["days_since_release"],
        payload["user_listened_artists"],
        uid,
    )
    final = finalize_discovery_ranking(
        scored,
        payload["candidate_ids"],
        payload["artist_by_song"],
    )
    section_ids = compose_discovery_sections(
        final["ranked_candidate_ids"],
        final["curated_ids"],
        scored_items=scored,
        artist_by_song=payload["artist_by_song"],
        candidate_pool_by_song=payload.get("candidate_pool_by_song", {}),
        low_exposure_reservoir=payload.get("low_exposure_reservoir", []),
        user_id=uid,
    )
    ranking_ms = (time.perf_counter() - t1) * 1000.0

    response = build_discovery_home_sections(
        db,
        section_ids,
        context_by_song=section_ids.get("_context_by_song"),
        section_microcopy=DISCOVERY_SECTION_MICROCOPY,
        anonymous=anonymous,
        timings_ms={
            "pool_ms": round(pool_ms, 3),
            "ranking_ms": round(ranking_ms, 3),
        },
    )
    response["request_id"] = request_id

    try:
        sample_request = random.random() < _DISCOVERY_IMPRESSION_SAMPLE_RATE
        inserted_impressions = 0
        if sample_request:
            inserted_impressions = _insert_discovery_impressions(
                db,
                request_id=request_id,
                uid=uid,
                section_ids=section_ids,
                scored=scored,
                artist_by_song=payload["artist_by_song"],
                candidate_pool_by_song=payload.get("candidate_pool_by_song", {}),
            )
        db.commit()
        if _is_development_env():
            logger.info(
                "Inserted %s discovery impressions (request_id=%s, sampled=%s)",
                inserted_impressions,
                request_id,
                sample_request,
            )
    except Exception:
        db.rollback()
        logger.exception("discovery_impression_insert_failed")

    return response


@router.post("/first-session")
def post_discovery_first_session(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    try:
        current = validate_onboarding_state(user.onboarding_step)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid onboarding state") from None
    if current == PREFERENCES_SET:
        user.onboarding_step = advance_onboarding_state(current, DISCOVERY_STARTED)
    elif current not in {DISCOVERY_STARTED, COMPLETED}:
        raise HTTPException(status_code=400, detail="Invalid onboarding transition")

    uid = int(user.id)
    payload = build_candidate_set(db, uid)
    scored = score_candidates(
        payload["candidate_ids"],
        payload["popularity"],
        payload["relevance"],
        payload["artist_by_song"],
        payload["days_since_release"],
        payload["user_listened_artists"],
        uid,
    )
    final = finalize_discovery_ranking(
        scored,
        payload["candidate_ids"],
        payload["artist_by_song"],
    )
    section_ids = compose_discovery_sections(
        final["ranked_candidate_ids"],
        final["curated_ids"],
        scored_items=scored,
        artist_by_song=payload["artist_by_song"],
        candidate_pool_by_song=payload.get("candidate_pool_by_song", {}),
        low_exposure_reservoir=payload.get("low_exposure_reservoir", []),
        user_id=uid,
    )
    hydrated = build_discovery_home_sections(
        db,
        section_ids,
        context_by_song=section_ids.get("_context_by_song"),
        section_microcopy=DISCOVERY_SECTION_MICROCOPY,
        anonymous=False,
    )

    profile = db.query(UserProfile).filter(UserProfile.user_id == uid).first()
    preferred_genres = set((profile.preferred_genres or []) if profile else [])
    preferred_artists = set((profile.preferred_artists or []) if profile else [])

    candidates = (
        list(hydrated.get("explore", []))
        + list(hydrated.get("for_you", []))
        + list(hydrated.get("play_now", []))
    )

    tracks: list[dict] = []
    seen_ids: set[int] = set()
    seen_artists: set[str] = set()
    for row in candidates:
        sid = int(row.get("id", 0))
        if sid <= 0 or sid in seen_ids or not bool(row.get("playable")):
            continue
        artist_name = str(row.get("artist_name") or "").strip().lower()
        if artist_name and artist_name in seen_artists:
            continue
        score_boost = 0
        if preferred_artists and str(row.get("artist_name") or "") in preferred_artists:
            score_boost += 2
        context = str(row.get("context_tag") or "")
        if "Hidden gem" in context:
            score_boost += 1
        if preferred_genres and any(g.lower() in str(row.get("title") or "").lower() for g in preferred_genres):
            score_boost += 1
        seen_ids.add(sid)
        if artist_name:
            seen_artists.add(artist_name)
        tracks.append({**row, "_boost": score_boost})
        if len(tracks) >= 12:
            break

    tracks = sorted(tracks, key=lambda x: int(x.get("_boost", 0)), reverse=True)
    for t in tracks:
        t.pop("_boost", None)

    db.commit()
    return {"tracks": tracks, "mode": "onboarding"}


@router.post("/events")
def post_discovery_event(
    body: DiscoveryPlayEventIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User | None, Depends(get_optional_user)],
):
    if body.event_type != "play_click":
        raise HTTPException(status_code=400, detail="Unsupported event_type")
    if not str(body.request_id or "").strip():
        raise HTTPException(status_code=400, detail="request_id required")

    artist_id = None
    if body.song_id is not None:
        row = db.query(Song.artist_id).filter(Song.id == int(body.song_id)).first()
        if row is not None and row[0] is not None:
            artist_id = int(row[0])

    metadata_json = {
        "ranking_version": str(body.ranking_version or _RANKING_VERSION),
        "auth_state": body.auth_state,
        "allowed_to_play": body.allowed_to_play,
        "blocked_reason": body.blocked_reason,
    }
    db.add(
        DiscoveryEvent(
            event_type="play_click",
            request_id=str(body.request_id).strip(),
            user_id=int(user.id) if user is not None else None,
            song_id=int(body.song_id) if body.song_id is not None else None,
            artist_id=artist_id,
            section=body.section,
            position=body.position,
            metadata_json=metadata_json,
        )
    )
    db.commit()
    if _is_development_env():
        logger.info(
            "Inserted discovery play_click (request_id=%s, song_id=%s, allowed=%s)",
            str(body.request_id).strip(),
            int(body.song_id) if body.song_id is not None else None,
            body.allowed_to_play,
        )
    return {"ok": True}


@router.get("/admin/analytics")
def get_discovery_admin_analytics(
    db: Annotated[Session, Depends(get_db)],
):
    try:
        db.execute(text("SELECT 1 FROM discovery_events LIMIT 1"))
    except OperationalError:
        logger.warning("discovery_admin_analytics_missing_table")
        return _empty_admin_analytics_payload()

    distinct_key_expr = (
        "COALESCE(CAST(request_id AS TEXT), '') || '-' || COALESCE(CAST(song_id AS TEXT), '')"
    )
    time_filter = "created_at >= datetime('now', '-1 day')"

    ctr_by_section_sql = text(
        f"""
        WITH imp AS (
          SELECT request_id, song_id, section, {distinct_key_expr} AS imp_key
          FROM discovery_events
          WHERE event_type = 'impression'
            AND {time_filter}
        ),
        clk AS (
          SELECT DISTINCT request_id, song_id, section
          FROM discovery_events
          WHERE event_type = 'play_click'
            AND {time_filter}
        )
        SELECT
          imp.section AS section,
          COUNT(DISTINCT imp.imp_key) AS impressions,
          COUNT(DISTINCT CASE WHEN clk.song_id IS NOT NULL THEN imp.imp_key END) AS clicks
        FROM imp
        LEFT JOIN clk
          ON clk.request_id = imp.request_id
         AND clk.song_id = imp.song_id
         AND COALESCE(clk.section, '') = COALESCE(imp.section, '')
        GROUP BY imp.section
        ORDER BY impressions DESC
        """
    )

    ctr_by_position_sql = text(
        f"""
        WITH imp AS (
          SELECT
            request_id,
            song_id,
            CAST(json_extract(metadata_json, '$.section_position_global') AS INTEGER) AS global_position,
            {distinct_key_expr} AS imp_key
          FROM discovery_events
          WHERE event_type = 'impression'
            AND {time_filter}
        ),
        clk AS (
          SELECT DISTINCT request_id, song_id
          FROM discovery_events
          WHERE event_type = 'play_click'
            AND {time_filter}
        )
        SELECT
          imp.global_position AS global_position,
          COUNT(DISTINCT imp.imp_key) AS impressions,
          COUNT(DISTINCT CASE WHEN clk.song_id IS NOT NULL THEN imp.imp_key END) AS clicks
        FROM imp
        LEFT JOIN clk
          ON clk.request_id = imp.request_id
         AND clk.song_id = imp.song_id
        WHERE imp.global_position IS NOT NULL
        GROUP BY imp.global_position
        ORDER BY imp.global_position ASC
        """
    )

    pool_performance_sql = text(
        f"""
        WITH imp AS (
          SELECT
            request_id,
            song_id,
            COALESCE(json_extract(metadata_json, '$.candidate_pool'), 'unknown') AS candidate_pool,
            {distinct_key_expr} AS imp_key
          FROM discovery_events
          WHERE event_type = 'impression'
            AND {time_filter}
        ),
        clk AS (
          SELECT DISTINCT request_id, song_id
          FROM discovery_events
          WHERE event_type = 'play_click'
            AND {time_filter}
        )
        SELECT
          imp.candidate_pool AS candidate_pool,
          COUNT(DISTINCT imp.imp_key) AS impressions,
          COUNT(DISTINCT CASE WHEN clk.song_id IS NOT NULL THEN imp.imp_key END) AS clicks
        FROM imp
        LEFT JOIN clk
          ON clk.request_id = imp.request_id
         AND clk.song_id = imp.song_id
        GROUP BY imp.candidate_pool
        ORDER BY impressions DESC
        """
    )

    pool_by_section_sql = text(
        f"""
        WITH imp AS (
          SELECT
            request_id,
            song_id,
            section,
            COALESCE(json_extract(metadata_json, '$.candidate_pool'), 'unknown') AS candidate_pool,
            {distinct_key_expr} AS imp_key
          FROM discovery_events
          WHERE event_type = 'impression'
            AND {time_filter}
        ),
        clk AS (
          SELECT DISTINCT request_id, song_id, section
          FROM discovery_events
          WHERE event_type = 'play_click'
            AND {time_filter}
        )
        SELECT
          imp.section AS section,
          imp.candidate_pool AS candidate_pool,
          COUNT(DISTINCT imp.imp_key) AS impressions,
          COUNT(DISTINCT CASE WHEN clk.song_id IS NOT NULL THEN imp.imp_key END) AS clicks
        FROM imp
        LEFT JOIN clk
          ON clk.request_id = imp.request_id
         AND clk.song_id = imp.song_id
         AND COALESCE(clk.section, '') = COALESCE(imp.section, '')
        GROUP BY imp.section, imp.candidate_pool
        ORDER BY imp.section ASC, impressions DESC
        """
    )

    ctr_by_ranking_version_sql = text(
        f"""
        WITH imp AS (
          SELECT
            request_id,
            song_id,
            COALESCE(json_extract(metadata_json, '$.ranking_version'), 'unknown') AS ranking_version,
            {distinct_key_expr} AS imp_key
          FROM discovery_events
          WHERE event_type = 'impression'
            AND {time_filter}
        ),
        clk AS (
          SELECT DISTINCT request_id, song_id
          FROM discovery_events
          WHERE event_type = 'play_click'
            AND {time_filter}
        )
        SELECT
          imp.ranking_version AS ranking_version,
          COUNT(DISTINCT imp.imp_key) AS impressions,
          COUNT(DISTINCT CASE WHEN clk.song_id IS NOT NULL THEN imp.imp_key END) AS clicks
        FROM imp
        LEFT JOIN clk
          ON clk.request_id = imp.request_id
         AND clk.song_id = imp.song_id
        GROUP BY imp.ranking_version
        ORDER BY impressions DESC
        """
    )

    top_artists_sql = text(
        f"""
        SELECT
          artist_id,
          COUNT(DISTINCT {distinct_key_expr}) AS impressions
        FROM discovery_events
        WHERE event_type = 'impression'
          AND {time_filter}
          AND artist_id IS NOT NULL
        GROUP BY artist_id
        ORDER BY impressions DESC
        LIMIT 10
        """
    )

    anomaly_sql = text(
        f"""
        WITH imp AS (
          SELECT
            request_id,
            song_id,
            artist_id,
            CAST(json_extract(metadata_json, '$.score_play_now') AS REAL) AS score_play_now,
            {distinct_key_expr} AS imp_key
          FROM discovery_events
          WHERE event_type = 'impression'
            AND {time_filter}
        ),
        clk AS (
          SELECT DISTINCT request_id, song_id
          FROM discovery_events
          WHERE event_type = 'play_click'
            AND {time_filter}
        )
        SELECT
          imp.song_id AS song_id,
          imp.artist_id AS artist_id,
          ROUND(AVG(COALESCE(imp.score_play_now, 0.0)), 6) AS avg_score_play_now,
          COUNT(DISTINCT imp.imp_key) AS impressions,
          COUNT(DISTINCT CASE WHEN clk.song_id IS NOT NULL THEN imp.imp_key END) AS clicks
        FROM imp
        LEFT JOIN clk
          ON clk.request_id = imp.request_id
         AND clk.song_id = imp.song_id
        GROUP BY imp.song_id, imp.artist_id
        HAVING COUNT(DISTINCT imp.imp_key) >= 50
           AND AVG(COALESCE(imp.score_play_now, 0.0)) >= 0.7
           AND (
             1.0 * COUNT(DISTINCT CASE WHEN clk.song_id IS NOT NULL THEN imp.imp_key END)
             / COUNT(DISTINCT imp.imp_key)
           ) <= 0.02
        ORDER BY impressions DESC
        LIMIT 100
        """
    )

    diversity_per_request_sql = text(
        f"""
        WITH per_request AS (
          SELECT
            request_id,
            COUNT(DISTINCT artist_id) AS unique_artists
          FROM discovery_events
          WHERE event_type = 'impression'
            AND {time_filter}
            AND artist_id IS NOT NULL
          GROUP BY request_id
        )
        SELECT
          ROUND(AVG(unique_artists), 6) AS avg_unique_artists,
          MIN(unique_artists) AS min_unique_artists,
          MAX(unique_artists) AS max_unique_artists
        FROM per_request
        """
    )

    score_ctr_correlation_sql = text(
        f"""
        WITH imp AS (
          SELECT
            request_id,
            song_id,
            CAST(json_extract(metadata_json, '$.score_play_now') AS REAL) AS score_play_now,
            {distinct_key_expr} AS imp_key
          FROM discovery_events
          WHERE event_type = 'impression'
            AND {time_filter}
        ),
        bucketed AS (
          SELECT
            request_id,
            song_id,
            imp_key,
            CASE
              WHEN COALESCE(score_play_now, 0.0) >= 0.8 THEN '0.8-1.0'
              WHEN COALESCE(score_play_now, 0.0) >= 0.6 THEN '0.6-0.8'
              WHEN COALESCE(score_play_now, 0.0) >= 0.4 THEN '0.4-0.6'
              WHEN COALESCE(score_play_now, 0.0) >= 0.2 THEN '0.2-0.4'
              ELSE '0.0-0.2'
            END AS bucket
          FROM imp
        ),
        clk AS (
          SELECT DISTINCT request_id, song_id
          FROM discovery_events
          WHERE event_type = 'play_click'
            AND {time_filter}
        )
        SELECT
          bucketed.bucket AS bucket,
          COUNT(DISTINCT bucketed.imp_key) AS impressions,
          COUNT(DISTINCT CASE WHEN clk.song_id IS NOT NULL THEN bucketed.imp_key END) AS clicks
        FROM bucketed
        LEFT JOIN clk
          ON clk.request_id = bucketed.request_id
         AND clk.song_id = bucketed.song_id
        GROUP BY bucketed.bucket
        ORDER BY CASE bucketed.bucket
          WHEN '0.8-1.0' THEN 1
          WHEN '0.6-0.8' THEN 2
          WHEN '0.4-0.6' THEN 3
          WHEN '0.2-0.4' THEN 4
          ELSE 5
        END
        """
    )

    quality_by_section_sql = text(
        f"""
        WITH impressions AS (
          SELECT
            request_id,
            song_id,
            COALESCE(section, 'unknown') AS section,
            {distinct_key_expr} AS imp_key
          FROM discovery_events
          WHERE event_type = 'impression'
            AND {time_filter}
        ),
        clicks AS (
          SELECT DISTINCT request_id, song_id, section
          FROM discovery_events
          WHERE event_type = 'play_click'
            AND {time_filter}
        ),
        session_pairs AS (
          SELECT
            discovery_request_id AS request_id,
            song_id,
            MAX(COALESCE(total_duration, 0)) AS session_duration
          FROM listening_sessions
          WHERE discovery_request_id IS NOT NULL
          GROUP BY discovery_request_id, song_id
        ),
        valid_pairs AS (
          SELECT DISTINCT
            ls.discovery_request_id AS request_id,
            ls.song_id
          FROM listening_sessions ls
          JOIN listening_events le
            ON le.session_id = ls.id
           AND le.is_valid = 1
          WHERE ls.discovery_request_id IS NOT NULL
        )
        SELECT
          impressions.section AS section,
          COUNT(DISTINCT CASE WHEN clicks.request_id IS NOT NULL THEN impressions.imp_key END) AS clicks,
          COUNT(DISTINCT CASE WHEN session_pairs.request_id IS NOT NULL THEN impressions.imp_key END) AS sessions,
          COUNT(DISTINCT CASE WHEN valid_pairs.request_id IS NOT NULL THEN impressions.imp_key END) AS valid_listens,
          AVG(CASE WHEN session_pairs.request_id IS NOT NULL THEN session_pairs.session_duration END) AS avg_session_duration_seconds,
          COUNT(DISTINCT CASE WHEN session_pairs.request_id IS NOT NULL AND session_pairs.session_duration < 10 THEN impressions.imp_key END) AS early_drops
        FROM impressions
        LEFT JOIN clicks
          ON clicks.request_id = impressions.request_id
         AND clicks.song_id = impressions.song_id
         AND COALESCE(clicks.section, '') = COALESCE(impressions.section, '')
        LEFT JOIN session_pairs
          ON session_pairs.request_id = impressions.request_id
         AND session_pairs.song_id = impressions.song_id
        LEFT JOIN valid_pairs
          ON valid_pairs.request_id = impressions.request_id
         AND valid_pairs.song_id = impressions.song_id
        GROUP BY impressions.section
        ORDER BY clicks DESC
        """
    )

    quality_by_pool_sql = text(
        f"""
        WITH impressions AS (
          SELECT
            request_id,
            song_id,
            COALESCE(json_extract(metadata_json, '$.candidate_pool'), 'unknown') AS candidate_pool,
            {distinct_key_expr} AS imp_key
          FROM discovery_events
          WHERE event_type = 'impression'
            AND {time_filter}
        ),
        clicks AS (
          SELECT DISTINCT request_id, song_id
          FROM discovery_events
          WHERE event_type = 'play_click'
            AND {time_filter}
        ),
        session_pairs AS (
          SELECT
            discovery_request_id AS request_id,
            song_id,
            MAX(COALESCE(total_duration, 0)) AS session_duration
          FROM listening_sessions
          WHERE discovery_request_id IS NOT NULL
          GROUP BY discovery_request_id, song_id
        ),
        valid_pairs AS (
          SELECT DISTINCT
            ls.discovery_request_id AS request_id,
            ls.song_id
          FROM listening_sessions ls
          JOIN listening_events le
            ON le.session_id = ls.id
           AND le.is_valid = 1
          WHERE ls.discovery_request_id IS NOT NULL
        )
        SELECT
          impressions.candidate_pool AS candidate_pool,
          COUNT(DISTINCT CASE WHEN clicks.request_id IS NOT NULL THEN impressions.imp_key END) AS clicks,
          COUNT(DISTINCT CASE WHEN session_pairs.request_id IS NOT NULL THEN impressions.imp_key END) AS sessions,
          COUNT(DISTINCT CASE WHEN valid_pairs.request_id IS NOT NULL THEN impressions.imp_key END) AS valid_listens,
          AVG(CASE WHEN session_pairs.request_id IS NOT NULL THEN session_pairs.session_duration END) AS avg_session_duration_seconds,
          COUNT(DISTINCT CASE WHEN session_pairs.request_id IS NOT NULL AND session_pairs.session_duration < 10 THEN impressions.imp_key END) AS early_drops
        FROM impressions
        LEFT JOIN clicks
          ON clicks.request_id = impressions.request_id
         AND clicks.song_id = impressions.song_id
        LEFT JOIN session_pairs
          ON session_pairs.request_id = impressions.request_id
         AND session_pairs.song_id = impressions.song_id
        LEFT JOIN valid_pairs
          ON valid_pairs.request_id = impressions.request_id
         AND valid_pairs.song_id = impressions.song_id
        GROUP BY impressions.candidate_pool
        ORDER BY clicks DESC
        """
    )

    quality_by_score_bucket_sql = text(
        f"""
        WITH impressions AS (
          SELECT
            request_id,
            song_id,
            CASE
              WHEN COALESCE(CAST(json_extract(metadata_json, '$.score_play_now') AS REAL), 0.0) >= 0.8 THEN '0.8-1.0'
              WHEN COALESCE(CAST(json_extract(metadata_json, '$.score_play_now') AS REAL), 0.0) >= 0.6 THEN '0.6-0.8'
              WHEN COALESCE(CAST(json_extract(metadata_json, '$.score_play_now') AS REAL), 0.0) >= 0.4 THEN '0.4-0.6'
              WHEN COALESCE(CAST(json_extract(metadata_json, '$.score_play_now') AS REAL), 0.0) >= 0.2 THEN '0.2-0.4'
              ELSE '0.0-0.2'
            END AS score_bucket,
            {distinct_key_expr} AS imp_key
          FROM discovery_events
          WHERE event_type = 'impression'
            AND {time_filter}
        ),
        clicks AS (
          SELECT DISTINCT request_id, song_id
          FROM discovery_events
          WHERE event_type = 'play_click'
            AND {time_filter}
        ),
        session_pairs AS (
          SELECT
            discovery_request_id AS request_id,
            song_id,
            MAX(COALESCE(total_duration, 0)) AS session_duration
          FROM listening_sessions
          WHERE discovery_request_id IS NOT NULL
          GROUP BY discovery_request_id, song_id
        ),
        valid_pairs AS (
          SELECT DISTINCT
            ls.discovery_request_id AS request_id,
            ls.song_id
          FROM listening_sessions ls
          JOIN listening_events le
            ON le.session_id = ls.id
           AND le.is_valid = 1
          WHERE ls.discovery_request_id IS NOT NULL
        )
        SELECT
          impressions.score_bucket AS score_bucket,
          COUNT(DISTINCT CASE WHEN clicks.request_id IS NOT NULL THEN impressions.imp_key END) AS clicks,
          COUNT(DISTINCT CASE WHEN session_pairs.request_id IS NOT NULL THEN impressions.imp_key END) AS sessions,
          COUNT(DISTINCT CASE WHEN valid_pairs.request_id IS NOT NULL THEN impressions.imp_key END) AS valid_listens,
          AVG(CASE WHEN session_pairs.request_id IS NOT NULL THEN session_pairs.session_duration END) AS avg_session_duration_seconds,
          COUNT(DISTINCT CASE WHEN session_pairs.request_id IS NOT NULL AND session_pairs.session_duration < 10 THEN impressions.imp_key END) AS early_drops
        FROM impressions
        LEFT JOIN clicks
          ON clicks.request_id = impressions.request_id
         AND clicks.song_id = impressions.song_id
        LEFT JOIN session_pairs
          ON session_pairs.request_id = impressions.request_id
         AND session_pairs.song_id = impressions.song_id
        LEFT JOIN valid_pairs
          ON valid_pairs.request_id = impressions.request_id
         AND valid_pairs.song_id = impressions.song_id
        GROUP BY impressions.score_bucket
        ORDER BY CASE impressions.score_bucket
          WHEN '0.8-1.0' THEN 1
          WHEN '0.6-0.8' THEN 2
          WHEN '0.4-0.6' THEN 3
          WHEN '0.2-0.4' THEN 4
          ELSE 5
        END
        """
    )

    listen_per_impression_by_section_sql = text(
        f"""
        WITH impressions AS (
          SELECT
            request_id,
            song_id,
            COALESCE(section, 'unknown') AS section,
            {distinct_key_expr} AS imp_key
          FROM discovery_events
          WHERE event_type = 'impression'
            AND {time_filter}
        ),
        valid_pairs AS (
          SELECT DISTINCT
            ls.discovery_request_id AS request_id,
            ls.song_id
          FROM listening_sessions ls
          JOIN listening_events le
            ON le.session_id = ls.id
           AND le.is_valid = 1
          WHERE ls.discovery_request_id IS NOT NULL
        )
        SELECT
          impressions.section AS section,
          COUNT(DISTINCT impressions.imp_key) AS impressions,
          COUNT(DISTINCT CASE WHEN valid_pairs.request_id IS NOT NULL THEN impressions.imp_key END) AS valid_listens
        FROM impressions
        LEFT JOIN valid_pairs
          ON valid_pairs.request_id = impressions.request_id
         AND valid_pairs.song_id = impressions.song_id
        GROUP BY impressions.section
        ORDER BY impressions DESC
        """
    )

    listen_per_impression_by_candidate_pool_sql = text(
        f"""
        WITH impressions AS (
          SELECT
            request_id,
            song_id,
            COALESCE(json_extract(metadata_json, '$.candidate_pool'), 'unknown') AS candidate_pool,
            {distinct_key_expr} AS imp_key
          FROM discovery_events
          WHERE event_type = 'impression'
            AND {time_filter}
        ),
        valid_pairs AS (
          SELECT DISTINCT
            ls.discovery_request_id AS request_id,
            ls.song_id
          FROM listening_sessions ls
          JOIN listening_events le
            ON le.session_id = ls.id
           AND le.is_valid = 1
          WHERE ls.discovery_request_id IS NOT NULL
        )
        SELECT
          impressions.candidate_pool AS candidate_pool,
          COUNT(DISTINCT impressions.imp_key) AS impressions,
          COUNT(DISTINCT CASE WHEN valid_pairs.request_id IS NOT NULL THEN impressions.imp_key END) AS valid_listens
        FROM impressions
        LEFT JOIN valid_pairs
          ON valid_pairs.request_id = impressions.request_id
         AND valid_pairs.song_id = impressions.song_id
        GROUP BY impressions.candidate_pool
        ORDER BY impressions DESC
        """
    )

    listen_per_impression_by_score_bucket_sql = text(
        f"""
        WITH impressions AS (
          SELECT
            request_id,
            song_id,
            CASE
              WHEN COALESCE(CAST(json_extract(metadata_json, '$.score_play_now') AS REAL), 0.0) >= 0.8 THEN '0.8-1.0'
              WHEN COALESCE(CAST(json_extract(metadata_json, '$.score_play_now') AS REAL), 0.0) >= 0.6 THEN '0.6-0.8'
              WHEN COALESCE(CAST(json_extract(metadata_json, '$.score_play_now') AS REAL), 0.0) >= 0.4 THEN '0.4-0.6'
              WHEN COALESCE(CAST(json_extract(metadata_json, '$.score_play_now') AS REAL), 0.0) >= 0.2 THEN '0.2-0.4'
              ELSE '0.0-0.2'
            END AS score_bucket,
            {distinct_key_expr} AS imp_key
          FROM discovery_events
          WHERE event_type = 'impression'
            AND {time_filter}
        ),
        valid_pairs AS (
          SELECT DISTINCT
            ls.discovery_request_id AS request_id,
            ls.song_id
          FROM listening_sessions ls
          JOIN listening_events le
            ON le.session_id = ls.id
           AND le.is_valid = 1
          WHERE ls.discovery_request_id IS NOT NULL
        )
        SELECT
          impressions.score_bucket AS score_bucket,
          COUNT(DISTINCT impressions.imp_key) AS impressions,
          COUNT(DISTINCT CASE WHEN valid_pairs.request_id IS NOT NULL THEN impressions.imp_key END) AS valid_listens
        FROM impressions
        LEFT JOIN valid_pairs
          ON valid_pairs.request_id = impressions.request_id
         AND valid_pairs.song_id = impressions.song_id
        GROUP BY impressions.score_bucket
        ORDER BY CASE impressions.score_bucket
          WHEN '0.8-1.0' THEN 1
          WHEN '0.6-0.8' THEN 2
          WHEN '0.4-0.6' THEN 3
          WHEN '0.2-0.4' THEN 4
          ELSE 5
        END
        """
    )

    valid_listen_per_click_by_section_sql = text(
        f"""
        WITH impressions AS (
          SELECT
            request_id,
            song_id,
            COALESCE(section, 'unknown') AS section,
            {distinct_key_expr} AS imp_key
          FROM discovery_events
          WHERE event_type = 'impression'
            AND {time_filter}
        ),
        clicks AS (
          SELECT DISTINCT request_id, song_id, section
          FROM discovery_events
          WHERE event_type = 'play_click'
            AND {time_filter}
        ),
        valid_pairs AS (
          SELECT DISTINCT
            ls.discovery_request_id AS request_id,
            ls.song_id
          FROM listening_sessions ls
          JOIN listening_events le
            ON le.session_id = ls.id
           AND le.is_valid = 1
          WHERE ls.discovery_request_id IS NOT NULL
        )
        SELECT
          impressions.section AS section,
          COUNT(DISTINCT CASE WHEN clicks.request_id IS NOT NULL THEN impressions.imp_key END) AS clicks,
          COUNT(DISTINCT CASE WHEN valid_pairs.request_id IS NOT NULL THEN impressions.imp_key END) AS valid_listens
        FROM impressions
        LEFT JOIN clicks
          ON clicks.request_id = impressions.request_id
         AND clicks.song_id = impressions.song_id
         AND COALESCE(clicks.section, '') = COALESCE(impressions.section, '')
        LEFT JOIN valid_pairs
          ON valid_pairs.request_id = impressions.request_id
         AND valid_pairs.song_id = impressions.song_id
        GROUP BY impressions.section
        ORDER BY clicks DESC
        """
    )

    ctr_by_section_rows = db.execute(ctr_by_section_sql).mappings().all()
    ctr_by_position_rows = db.execute(ctr_by_position_sql).mappings().all()
    pool_performance_rows = db.execute(pool_performance_sql).mappings().all()
    pool_by_section_rows = db.execute(pool_by_section_sql).mappings().all()
    ctr_by_ranking_version_rows = db.execute(ctr_by_ranking_version_sql).mappings().all()
    top_artist_rows = db.execute(top_artists_sql).mappings().all()
    anomaly_rows = db.execute(anomaly_sql).mappings().all()
    diversity_row = db.execute(diversity_per_request_sql).mappings().first()
    score_ctr_correlation_rows = db.execute(score_ctr_correlation_sql).mappings().all()
    quality_by_section_rows = db.execute(quality_by_section_sql).mappings().all()
    quality_by_pool_rows = db.execute(quality_by_pool_sql).mappings().all()
    quality_by_score_bucket_rows = db.execute(
        quality_by_score_bucket_sql
    ).mappings().all()
    listen_per_impression_by_section_rows = db.execute(
        listen_per_impression_by_section_sql
    ).mappings().all()
    listen_per_impression_by_candidate_pool_rows = db.execute(
        listen_per_impression_by_candidate_pool_sql
    ).mappings().all()
    listen_per_impression_by_score_bucket_rows = db.execute(
        listen_per_impression_by_score_bucket_sql
    ).mappings().all()
    valid_listen_per_click_by_section_rows = db.execute(
        valid_listen_per_click_by_section_sql
    ).mappings().all()

    total_impressions = int(
        db.execute(
            text(
                f"""
                SELECT COUNT(DISTINCT {distinct_key_expr})
                FROM discovery_events
                WHERE event_type = 'impression'
                  AND {time_filter}
                """
            )
        ).scalar()
        or 0
    )

    ctr_by_section = [
        {
            "section": str(row["section"] or "unknown"),
            "impressions": int(row["impressions"] or 0),
            "clicks": int(row["clicks"] or 0),
            "ctr": _float_ratio(int(row["clicks"] or 0), int(row["impressions"] or 0)),
        }
        for row in ctr_by_section_rows
    ]

    ctr_by_position = [
        {
            "global_position": int(row["global_position"]),
            "impressions": int(row["impressions"] or 0),
            "clicks": int(row["clicks"] or 0),
            "ctr": _float_ratio(int(row["clicks"] or 0), int(row["impressions"] or 0)),
        }
        for row in ctr_by_position_rows
    ]

    candidate_pool_performance = [
        {
            "candidate_pool": str(row["candidate_pool"] or "unknown"),
            "impressions": int(row["impressions"] or 0),
            "clicks": int(row["clicks"] or 0),
            "ctr": _float_ratio(int(row["clicks"] or 0), int(row["impressions"] or 0)),
        }
        for row in pool_performance_rows
    ]

    section_totals: dict[str, int] = {}
    for row in pool_by_section_rows:
        section = str(row["section"] or "unknown")
        section_totals[section] = section_totals.get(section, 0) + int(
            row["impressions"] or 0
        )
    candidate_pool_by_section = [
        {
            "section": str(row["section"] or "unknown"),
            "candidate_pool": str(row["candidate_pool"] or "unknown"),
            "impressions": int(row["impressions"] or 0),
            "clicks": int(row["clicks"] or 0),
            "ctr": _float_ratio(int(row["clicks"] or 0), int(row["impressions"] or 0)),
            "share": _float_ratio(
                int(row["impressions"] or 0),
                section_totals.get(str(row["section"] or "unknown"), 0),
            ),
        }
        for row in pool_by_section_rows
    ]

    ctr_by_ranking_version = [
        {
            "ranking_version": str(row["ranking_version"] or "unknown"),
            "impressions": int(row["impressions"] or 0),
            "clicks": int(row["clicks"] or 0),
            "ctr": _float_ratio(int(row["clicks"] or 0), int(row["impressions"] or 0)),
        }
        for row in ctr_by_ranking_version_rows
    ]

    top_artists = [
        {
            "artist_id": int(row["artist_id"]),
            "impressions": int(row["impressions"] or 0),
            "share": _float_ratio(int(row["impressions"] or 0), total_impressions),
        }
        for row in top_artist_rows
        if row["artist_id"] is not None
    ]
    top_artists_share = round(sum((float(r["share"]) for r in top_artists)), 6)

    anomalies = [
        {
            "song_id": int(row["song_id"]),
            "artist_id": int(row["artist_id"]) if row["artist_id"] is not None else None,
            "avg_score_play_now": float(row["avg_score_play_now"] or 0.0),
            "impressions": int(row["impressions"] or 0),
            "clicks": int(row["clicks"] or 0),
            "ctr": _float_ratio(int(row["clicks"] or 0), int(row["impressions"] or 0)),
        }
        for row in anomaly_rows
    ]

    diversity_per_request = {
        "avg_unique_artists": float(
            (diversity_row["avg_unique_artists"] if diversity_row else 0.0) or 0.0
        ),
        "min_unique_artists": int(
            (diversity_row["min_unique_artists"] if diversity_row else 0) or 0
        ),
        "max_unique_artists": int(
            (diversity_row["max_unique_artists"] if diversity_row else 0) or 0
        ),
    }

    score_ctr_correlation = [
        {
            "bucket": str(row["bucket"]),
            "impressions": int(row["impressions"] or 0),
            "clicks": int(row["clicks"] or 0),
            "ctr": _float_ratio(int(row["clicks"] or 0), int(row["impressions"] or 0)),
        }
        for row in score_ctr_correlation_rows
    ]

    quality_by_section = [
        {
            "section": str(row["section"] or "unknown"),
            "clicks": int(row["clicks"] or 0),
            "sessions": int(row["sessions"] or 0),
            "valid_listens": int(row["valid_listens"] or 0),
            "session_rate": _float_ratio(int(row["sessions"] or 0), int(row["clicks"] or 0)),
            "valid_listen_rate": _float_ratio(
                int(row["valid_listens"] or 0), int(row["clicks"] or 0)
            ),
            "avg_session_duration_seconds": float(
                row["avg_session_duration_seconds"] or 0.0
            ),
            "early_drop_rate": _float_ratio(
                int(row["early_drops"] or 0), int(row["sessions"] or 0)
            ),
        }
        for row in quality_by_section_rows
    ]

    quality_by_candidate_pool = [
        {
            "candidate_pool": str(row["candidate_pool"] or "unknown"),
            "clicks": int(row["clicks"] or 0),
            "sessions": int(row["sessions"] or 0),
            "valid_listens": int(row["valid_listens"] or 0),
            "session_rate": _float_ratio(int(row["sessions"] or 0), int(row["clicks"] or 0)),
            "valid_listen_rate": _float_ratio(
                int(row["valid_listens"] or 0), int(row["clicks"] or 0)
            ),
            "avg_session_duration_seconds": float(
                row["avg_session_duration_seconds"] or 0.0
            ),
            "early_drop_rate": _float_ratio(
                int(row["early_drops"] or 0), int(row["sessions"] or 0)
            ),
        }
        for row in quality_by_pool_rows
    ]

    quality_by_score_bucket = [
        {
            "score_bucket": str(row["score_bucket"] or "0.0-0.2"),
            "clicks": int(row["clicks"] or 0),
            "sessions": int(row["sessions"] or 0),
            "valid_listens": int(row["valid_listens"] or 0),
            "session_rate": _float_ratio(int(row["sessions"] or 0), int(row["clicks"] or 0)),
            "valid_listen_rate": _float_ratio(
                int(row["valid_listens"] or 0), int(row["clicks"] or 0)
            ),
            "avg_session_duration_seconds": float(
                row["avg_session_duration_seconds"] or 0.0
            ),
            "early_drop_rate": _float_ratio(
                int(row["early_drops"] or 0), int(row["sessions"] or 0)
            ),
        }
        for row in quality_by_score_bucket_rows
    ]

    listen_per_impression_by_section = [
        {
            "section": str(row["section"] or "unknown"),
            "impressions": int(row["impressions"] or 0),
            "valid_listens": int(row["valid_listens"] or 0),
            "listen_per_impression": _float_ratio(
                int(row["valid_listens"] or 0), int(row["impressions"] or 0)
            ),
        }
        for row in listen_per_impression_by_section_rows
    ]

    listen_per_impression_by_candidate_pool = [
        {
            "candidate_pool": str(row["candidate_pool"] or "unknown"),
            "impressions": int(row["impressions"] or 0),
            "valid_listens": int(row["valid_listens"] or 0),
            "listen_per_impression": _float_ratio(
                int(row["valid_listens"] or 0), int(row["impressions"] or 0)
            ),
        }
        for row in listen_per_impression_by_candidate_pool_rows
    ]

    listen_per_impression_by_score_bucket = [
        {
            "score_bucket": str(row["score_bucket"] or "0.0-0.2"),
            "impressions": int(row["impressions"] or 0),
            "valid_listens": int(row["valid_listens"] or 0),
            "listen_per_impression": _float_ratio(
                int(row["valid_listens"] or 0), int(row["impressions"] or 0)
            ),
        }
        for row in listen_per_impression_by_score_bucket_rows
    ]

    valid_listen_per_click_by_section = [
        {
            "section": str(row["section"] or "unknown"),
            "clicks": int(row["clicks"] or 0),
            "valid_listens": int(row["valid_listens"] or 0),
            "valid_listen_per_click": _float_ratio(
                int(row["valid_listens"] or 0), int(row["clicks"] or 0)
            ),
        }
        for row in valid_listen_per_click_by_section_rows
    ]

    return {
        "ctr_by_section": ctr_by_section,
        "ctr_by_position": ctr_by_position,
        "candidate_pool_performance": candidate_pool_performance,
        "candidate_pool_by_section": candidate_pool_by_section,
        "ctr_by_ranking_version": ctr_by_ranking_version,
        "top_artists_concentration": {
            "top_artists": top_artists,
            "top_artists_share": top_artists_share,
            "total_impressions": total_impressions,
        },
        "high_score_low_ctr_anomalies": anomalies,
        "diversity_per_request": diversity_per_request,
        "score_ctr_correlation": score_ctr_correlation,
        "quality_by_section": quality_by_section,
        "quality_by_candidate_pool": quality_by_candidate_pool,
        "quality_by_score_bucket": quality_by_score_bucket,
        "listen_per_impression_by_section": listen_per_impression_by_section,
        "listen_per_impression_by_candidate_pool": listen_per_impression_by_candidate_pool,
        "listen_per_impression_by_score_bucket": listen_per_impression_by_score_bucket,
        "valid_listen_per_click_by_section": valid_listen_per_click_by_section,
    }


@router.get("/debug/telemetry-check")
def get_discovery_telemetry_check(
    db: Annotated[Session, Depends(get_db)],
):
    if not _is_development_env():
        raise HTTPException(status_code=404, detail="Not found")

    has_table = False
    try:
        has_table = (
            db.execute(
                text(
                    """
                    SELECT 1
                    FROM sqlite_master
                    WHERE type='table' AND name='discovery_events'
                    LIMIT 1
                    """
                )
            ).first()
            is not None
        )
    except Exception:
        logger.exception("discovery_telemetry_check_table_probe_failed")

    if not has_table:
        return {
            "has_discovery_events_table": False,
            "total_rows": 0,
            "impressions_last_1h": 0,
            "clicks_last_1h": 0,
        }

    total_rows = int(
        db.execute(text("SELECT COUNT(*) FROM discovery_events")).scalar() or 0
    )
    impressions_last_1h = int(
        db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM discovery_events
                WHERE event_type = 'impression'
                  AND created_at >= datetime('now', '-1 hour')
                """
            )
        ).scalar()
        or 0
    )
    clicks_last_1h = int(
        db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM discovery_events
                WHERE event_type = 'play_click'
                  AND created_at >= datetime('now', '-1 hour')
                """
            )
        ).scalar()
        or 0
    )
    return {
        "has_discovery_events_table": True,
        "total_rows": total_rows,
        "impressions_last_1h": impressions_last_1h,
        "clicks_last_1h": clicks_last_1h,
    }
