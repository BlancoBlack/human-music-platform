"""
Discovery API: ranked home sections with hydrated track rows.
"""

from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_optional_user
from app.core.database import get_db
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
        user_id=uid,
    )
    ranking_ms = (time.perf_counter() - t1) * 1000.0

    return build_discovery_home_sections(
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
