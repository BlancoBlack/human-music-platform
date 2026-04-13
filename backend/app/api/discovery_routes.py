"""
Discovery API: ranked home sections with hydrated track rows.
"""

from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_optional_user
from app.core.database import get_db
from app.models.user import User
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
