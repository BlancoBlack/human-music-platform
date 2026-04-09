"""
ListeningEvent economic validation rules (Phase 1: enrichment only).

This module must not change aggregation or payout behavior. It only computes
validation metadata to be stored on `ListeningEvent`.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any, Dict

from app.models.listening_event import ListeningEvent


def validate_listen(
    user_id: int,
    song: Any,
    raw_duration: int,
    db: Any,
    now_utc: Any,
) -> Dict[str, Any]:
    """
    Compute economic validation metadata for one listen.

    Repeat counting uses `ListeningEvent.created_at` (server-side time) and
    counts only prior events (the caller should invoke this before inserting
    the current ListeningEvent).
    """

    # Step 1 — REAL DURATION
    song_duration = getattr(song, "duration_seconds", None) or getattr(
        song, "duration", None
    )
    if not song_duration or float(song_duration) <= 0:
        has_song_duration = False
    else:
        has_song_duration = True

    if has_song_duration:
        real_duration = float(min(raw_duration, float(song_duration)))
    else:
        real_duration = float(raw_duration)

    # Step 2 — THRESHOLD
    if has_song_duration:
        threshold = max(30.0, 0.3 * float(song_duration))
    else:
        threshold = 30.0

    # Step 3 — DURATION VALIDITY
    is_valid = real_duration >= float(threshold)

    # Step 4 — VALIDATED DURATION (duration gate only)
    validated_duration = real_duration if is_valid else 0.0

    if not is_valid:
        tokens_invalid: list[str] = []
        if not has_song_duration:
            tokens_invalid.append("missing_song_duration")
        tokens_invalid.append("invalid_below_threshold")
        return {
            "is_valid": False,
            "validated_duration": 0.0,
            "weight": 0.0,
            "validation_reason": "+".join(tokens_invalid),
        }

    # Step 5 — SPACING (>= 2h since last valid listen for this user + song)
    last_valid = (
        db.query(ListeningEvent)
        .filter(
            ListeningEvent.user_id == user_id,
            ListeningEvent.song_id == song.id,
            ListeningEvent.is_valid.is_(True),
        )
        .order_by(ListeningEvent.created_at.desc())
        .limit(1)
        .first()
    )
    if last_valid is not None and last_valid.created_at is not None:
        time_diff = now_utc - last_valid.created_at
        if time_diff < timedelta(hours=2):
            return {
                "is_valid": False,
                "validated_duration": 0.0,
                "weight": 0.0,
                "validation_reason": "too_soon_repeat",
            }

    # Step 6 — DAILY CAP (max 5 valid listens per UTC calendar day)
    day_start = datetime(now_utc.year, now_utc.month, now_utc.day)
    day_end = day_start + timedelta(days=1)
    valid_today_count = (
        db.query(ListeningEvent.id)
        .filter(
            ListeningEvent.user_id == user_id,
            ListeningEvent.song_id == song.id,
            ListeningEvent.is_valid.is_(True),
            ListeningEvent.created_at >= day_start,
            ListeningEvent.created_at < day_end,
        )
        .count()
    )
    if valid_today_count >= 5:
        return {
            "is_valid": False,
            "validated_duration": 0.0,
            "weight": 0.0,
            "validation_reason": "daily_cap_exceeded",
        }

    # Step 7 — REPEAT COUNT (24h) — unchanged formula
    last_24h = now_utc - timedelta(hours=24)
    repeats = (
        db.query(ListeningEvent.id)
        .filter(
            ListeningEvent.user_id == user_id,
            ListeningEvent.song_id == song.id,
            ListeningEvent.is_valid.is_(True),
            ListeningEvent.created_at >= last_24h,
        )
        .count()
    )

    repeats = max(0, repeats)

    # Step 8 — WEIGHT — unchanged formula
    weight = math.exp(-0.22 * float(repeats))

    # Step 9 — VALIDATION REASON (duration-valid path only)
    tokens: list[str] = []
    if not has_song_duration:
        tokens.append("missing_song_duration")

    if not has_song_duration:
        tokens.append("valid_absolute")
    else:
        abs_threshold = 30.0
        pct_threshold = 0.3 * float(song_duration)
        epsilon = 1e-9

        if abs(pct_threshold - abs_threshold) <= epsilon:
            tokens.extend(["valid_absolute", "valid_percentage"])
        elif pct_threshold > abs_threshold:
            tokens.append("valid_percentage")
        else:
            tokens.append("valid_absolute")

    validation_reason = "+".join(tokens)

    return {
        "is_valid": True,
        "validated_duration": float(validated_duration),
        "weight": float(weight),
        "validation_reason": validation_reason,
    }

