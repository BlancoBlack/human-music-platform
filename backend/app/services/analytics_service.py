"""
Artist analytics: money-based time series derived from user pool distribution,
not raw listening duration totals.

Conservation: for each user/song, sum of daily amounts equals ``song_payout`` from
``calculate_user_distribution`` (before per-artist split), using remainder
allocation at aggregate and day boundaries so float drift does not leak money.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import Integer, distinct, func

from app.core.database import SessionLocal
from app.models.listening_aggregate import ListeningAggregate
from app.models.listening_event import ListeningEvent
from app.models.song import Song
from app.models.user import User
from app.models.user_balance import UserBalance
from app.services.payout_service import calculate_user_distribution, is_system_song
from app.services.song_split_distribution import split_song_amount_to_artists

# Tolerance for float conservation checks (not used to alter amounts).
_CONSERVATION_EPS = 1e-9

_STREAMS_RANGE_TO_DAYS = {
    "last_day": 1,
    "last_week": 7,
    "last_30_days": 30,
    "last_3_months": 90,
    "last_6_months": 180,
    "last_12_months": 365,
    "last_2_years": 730,
    "last_5_years": 1825,
}


def _song_is_system(db: Any, song_id: Optional[int], cache: dict[int, bool]) -> bool:
    if song_id is None:
        return True
    sid = int(song_id)
    if sid in cache:
        return cache[sid]
    song = db.query(Song).filter(Song.id == sid).first()
    cache[sid] = is_system_song(song)
    return cache[sid]


def _valid_stream_filter_conditions() -> tuple[Any, ...]:
    """
    Canonical analytics stream filter: economically valid listen events only.
    """
    return (
        ListeningEvent.is_valid.is_(True),
        ListeningEvent.validated_duration > 0,
    )


def _resolve_utc_range(range: str) -> Tuple[datetime, datetime]:
    if range not in _STREAMS_RANGE_TO_DAYS:
        raise ValueError(
            "Invalid range. Use one of: last_day, last_week, last_30_days, "
            "last_3_months, last_6_months, last_12_months, last_2_years, last_5_years."
        )
    now_utc = datetime.utcnow()
    start_utc = now_utc - timedelta(days=_STREAMS_RANGE_TO_DAYS[range])
    return start_utc, now_utc


def _split_amount_with_remainder_last(
    weights: list[float],
    total_amount: float,
) -> list[float]:
    """
    Allocate ``total_amount`` across ``weights`` proportionally; assign rounding
    remainder to the **last** index so ``sum(result) == total_amount`` exactly.
    """
    s = float(sum(weights))
    if s <= 0:
        return [0.0] * len(weights)
    if len(weights) == 1:
        return [float(total_amount)]
    out: list[float] = []
    acc = 0.0
    for w in weights[:-1]:
        part = float(total_amount) * (float(w) / s)
        out.append(part)
        acc += part
    out.append(float(total_amount) - acc)
    return out


def _distribute_song_payout_to_days(
    song_payout: float,
    day_rows: list[tuple[object, float | None]],
) -> dict[str, float]:
    """
    Map calendar day -> money such that sum(values) == ``song_payout`` exactly.

    ``day_rows`` are (day_key, duration_sum) sorted by day string for stable
    remainder placement; last day absorbs any float remainder.
    """
    cleaned: list[tuple[str, float]] = []
    for day_val, dur in sorted(day_rows, key=lambda x: str(x[0])):
        if dur is None:
            continue
        d = float(dur)
        if d > 0:
            cleaned.append((str(day_val), d))
    if not cleaned:
        return {}
    if len(cleaned) == 1:
        return {cleaned[0][0]: float(song_payout)}
    weights = [d for _, d in cleaned]
    amounts = _split_amount_with_remainder_last(weights, song_payout)
    return {cleaned[i][0]: amounts[i] for i in range(len(cleaned))}


def get_artist_earnings_over_time(artist_id: int) -> dict[str, float]:
    """
    Estimate how much of each user's monthly pool accrues to ``artist_id`` per
    calendar day, using the same distribution rules as payouts (but without
    reading ledger payout rows).

    Money conservation (per user/song): sum of daily slices for that song
    equals ``entry['payout']`` from ``calculate_user_distribution`` (then
    linear per-artist split applies per day).

    Returns mapping ``YYYY-MM-DD`` -> euros (rounded only in the output).
    """
    db = SessionLocal()
    earnings_by_day: defaultdict[str, float] = defaultdict(float)
    song_system_cache: dict[int, bool] = {}

    try:
        balances = db.query(UserBalance).all()

        for ub in balances:
            user_id = ub.user_id
            distribution = calculate_user_distribution(user_id)

            for entry in distribution:
                song_id = entry["song_id"]
                if _song_is_system(db, song_id, song_system_cache):
                    continue
                song_payout = float(entry["payout"])

                aggs = (
                    db.query(ListeningAggregate)
                    .filter_by(user_id=user_id, song_id=song_id)
                    .order_by(ListeningAggregate.id)
                    .all()
                )
                if not aggs:
                    continue

                total_agg_duration = float(
                    sum(float(a.total_duration or 0) for a in aggs)
                )
                if total_agg_duration <= 0:
                    continue

                if (
                    split_song_amount_to_artists(db, song_id, song_payout).get(
                        artist_id, 0.0
                    )
                    == 0
                ):
                    continue

                # 1) Split song_payout across aggregate rows; remainder on last aggregate.
                agg_weights = [float(a.total_duration or 0) for a in aggs]
                agg_payouts = _split_amount_with_remainder_last(
                    agg_weights, song_payout
                )
                if (
                    abs(sum(agg_payouts) - song_payout) > _CONSERVATION_EPS
                    and len(agg_payouts) > 0
                ):
                    # Should not happen; fail fast if float logic regresses.
                    raise RuntimeError(
                        "Internal conservation error: aggregate split != song_payout"
                    )

                day_col = func.date(
                    func.coalesce(
                        ListeningEvent.created_at,
                        ListeningEvent.timestamp,
                    )
                )
                rows = (
                    db.query(
                        day_col,
                        func.sum(
                            func.coalesce(ListeningEvent.validated_duration, 0.0)
                            * func.coalesce(ListeningEvent.weight, 0.0)
                        ),
                    )
                    .filter(
                        ListeningEvent.user_id == user_id,
                        ListeningEvent.song_id == song_id,
                        *_valid_stream_filter_conditions(),
                    )
                    .group_by(day_col)
                    .all()
                )
                if not rows:
                    continue

                total_event_units = sum(
                    float(d or 0) for _, d in rows if d is not None
                )
                if total_event_units <= 0:
                    continue

                # 2) For each aggregate row's share of money, assign to calendar days using
                #    qualified event units (validated_duration * weight). Remainder on the
                #    last day per slice.
                #    Summing over aggregates: sum(day_money) == song_payout exactly.
                day_to_money: dict[str, float] = defaultdict(float)
                for agg_payout in agg_payouts:
                    part = _distribute_song_payout_to_days(agg_payout, list(rows))
                    for day_str, m in part.items():
                        day_to_money[day_str] += m

                if (
                    abs(sum(day_to_money.values()) - song_payout) > _CONSERVATION_EPS
                    and day_to_money
                ):
                    raise RuntimeError(
                        "Internal conservation error: day split != song_payout"
                    )

                for day_str, day_money in day_to_money.items():
                    artist_part = split_song_amount_to_artists(
                        db, song_id, day_money
                    ).get(artist_id, 0.0)
                    earnings_by_day[day_str] += artist_part

        return _apply_display_rounding_consistency(earnings_by_day)

    finally:
        db.close()


def _apply_display_rounding_consistency(
    earnings_by_day: dict[str, float],
) -> dict[str, float]:
    """
    Round each day to 2 decimals, then nudge the **last** chronological day so that
    ``sum(displayed)`` matches ``sum(unrounded)`` after cent-level reconciliation (UI only).
    """
    items = sorted(earnings_by_day.items(), key=lambda x: str(x[0]))
    if not items:
        return {}

    exact_total = sum(float(v) for _, v in items)
    rounded_rows: list[tuple[str, float]] = [
        (str(d), round(float(v), 2)) for d, v in items
    ]
    rounded_total = sum(r for _, r in rounded_rows)
    diff = round(exact_total - rounded_total, 2)

    if diff != 0:
        last_date, last_amt = rounded_rows[-1]
        rounded_rows[-1] = (last_date, round(last_amt + diff, 2))

    return {d: amt for d, amt in rounded_rows}


def get_artist_estimated_total(artist_id: int) -> float:
    """
    Real-time estimated earnings for ``artist_id`` (analytics model only).

    Sums, over every subscriber, this artist's share of each song line from
    ``calculate_user_distribution`` via ``split_song_amount_to_artists`` — same
    economic path as ``get_artist_earnings_over_time``, without time bucketing.

    ``sum(get_artist_earnings_over_time(artist_id).values())`` matches this value
    after display rounding reconciliation (typically exact to 2 decimals).
    """
    db = SessionLocal()
    song_system_cache: dict[int, bool] = {}
    try:
        total = 0.0
        for ub in db.query(UserBalance).all():
            distribution = calculate_user_distribution(ub.user_id)
            for entry in distribution:
                song_id = entry.get("song_id")
                if _song_is_system(db, song_id, song_system_cache):
                    continue
                per_artist = split_song_amount_to_artists(
                    db,
                    song_id,
                    float(entry["payout"]),
                )
                total += per_artist.get(artist_id, 0.0)
        return round(total, 2)
    finally:
        db.close()


def get_artist_estimated_earnings_by_song(artist_id: int) -> list[dict]:
    """
    Per-song estimated amounts for ``artist_id`` (analytics model only).

    Aggregates ``split_song_amount_to_artists`` applied to each
    ``calculate_user_distribution`` line, summed by ``song_id``.
    """
    db = SessionLocal()
    song_system_cache: dict[int, bool] = {}
    try:
        by_song: defaultdict[int, float] = defaultdict(float)
        for ub in db.query(UserBalance).all():
            distribution = calculate_user_distribution(ub.user_id)
            for entry in distribution:
                song_id = entry.get("song_id")
                if _song_is_system(db, song_id, song_system_cache):
                    continue
                per_artist = split_song_amount_to_artists(
                    db,
                    song_id,
                    float(entry["payout"]),
                )
                amt = per_artist.get(artist_id, 0.0)
                if amt:
                    by_song[int(song_id)] += amt
        ranked = sorted(by_song.items(), key=lambda x: -x[1])
        return [
            {"song_id": int(sid), "estimated": round(val, 2)}
            for sid, val in ranked
        ]
    finally:
        db.close()


def get_artist_streams_over_time(
    artist_id: int,
    range: str = "last_30_days",
    song_id: Optional[int] = None,
) -> Dict[str, int]:
    """
    Streams analytics from ListeningEvent only.

    Stream definition: one economically valid ListeningEvent.
    All analytics are calculated in UTC.
    """
    db = SessionLocal()
    try:
        start_utc, now_utc = _resolve_utc_range(range)

        # Optional song filter must belong to the artist; otherwise return empty result.
        if song_id is not None:
            owned_song = (
                db.query(Song.id)
                .filter(Song.id == song_id, Song.artist_id == artist_id)
                .first()
            )
            if not owned_song:
                return {}

        if range in {"last_day", "last_week"}:
            bucket = func.strftime("%Y-%m-%dT%H:00", ListeningEvent.created_at)
        elif range in {"last_30_days", "last_3_months"}:
            bucket = func.strftime("%Y-%m-%d", ListeningEvent.created_at)
        elif range == "last_6_months":
            # 3-day UTC buckets anchored to Unix epoch.
            epoch = func.cast(func.strftime("%s", ListeningEvent.created_at), Integer)
            bucket_start = func.datetime((epoch / 259200) * 259200, "unixepoch")
            bucket = func.strftime("%Y-%m-%d", bucket_start)
        elif range == "last_12_months":
            bucket = func.strftime("%Y-W%W", ListeningEvent.created_at)
        else:
            bucket = func.strftime("%Y-%m", ListeningEvent.created_at)

        query = (
            db.query(bucket.label("bucket"), func.count(ListeningEvent.id).label("valid_streams"))
            .join(Song, Song.id == ListeningEvent.song_id)
            .filter(
                Song.artist_id == artist_id,
                *_valid_stream_filter_conditions(),
                ListeningEvent.created_at >= start_utc,
                ListeningEvent.created_at <= now_utc,
            )
        )
        if song_id is not None:
            query = query.filter(ListeningEvent.song_id == song_id)

        rows = query.group_by(bucket).order_by(bucket.asc()).all()
        if not rows:
            return {}

        return {
            str(bucket_key): int(valid_streams)
            for bucket_key, valid_streams in rows
            if bucket_key is not None
        }
    finally:
        db.close()


def get_artist_top_songs(
    artist_id: int,
    range: str = "last_30_days",
) -> List[dict]:
    """
    Top songs analytics from ListeningEvent only.

    Stream definition: one economically valid ListeningEvent.
    All analytics are calculated in UTC.
    """
    db = SessionLocal()
    try:
        start_utc, now_utc = _resolve_utc_range(range)

        rows = (
            db.query(
                Song.id.label("song_id"),
                Song.title.label("title"),
                func.count(ListeningEvent.id).label("valid_streams"),
            )
            .join(Song, Song.id == ListeningEvent.song_id)
            .filter(
                Song.artist_id == artist_id,
                *_valid_stream_filter_conditions(),
                ListeningEvent.created_at >= start_utc,
                ListeningEvent.created_at <= now_utc,
            )
            .group_by(Song.id, Song.title)
            .order_by(func.count(ListeningEvent.id).desc(), Song.id.asc())
            .limit(20)
            .all()
        )
        if not rows:
            return []

        return [
            {
                "song_id": int(song_id),
                "title": title,
                "streams": int(valid_streams),
            }
            for song_id, title, valid_streams in rows
        ]
    finally:
        db.close()


def get_artist_top_fans(
    artist_id: int,
    range: str = "last_30_days",
) -> List[dict]:
    """
    Top fans by stream count from ListeningEvent only.

    Stream definition: one economically valid ListeningEvent.
    Uses INNER JOIN User; username falls back to \"Unknown user\" when null/blank.
    All analytics are calculated in UTC.
    """
    db = SessionLocal()
    try:
        start_utc, now_utc = _resolve_utc_range(range)

        step1 = (
            db.query(
                ListeningEvent.user_id,
                func.max(User.username).label("username"),
                func.count(ListeningEvent.id).label("valid_streams"),
            )
            .join(Song, Song.id == ListeningEvent.song_id)
            .join(User, User.id == ListeningEvent.user_id)
            .filter(
                Song.artist_id == artist_id,
                *_valid_stream_filter_conditions(),
                ListeningEvent.created_at >= start_utc,
                ListeningEvent.created_at <= now_utc,
                ListeningEvent.user_id.isnot(None),
            )
            .group_by(ListeningEvent.user_id)
            .order_by(
                func.count(ListeningEvent.id).desc(),
                ListeningEvent.user_id.asc(),
            )
            .limit(20)
            .all()
        )
        if not step1:
            return []

        user_ids = [int(uid) for uid, _username, _streams in step1]

        song_rows = (
            db.query(
                ListeningEvent.user_id,
                Song.id.label("song_id"),
                Song.title.label("title"),
                func.count(ListeningEvent.id).label("valid_streams"),
            )
            .join(Song, Song.id == ListeningEvent.song_id)
            .join(User, User.id == ListeningEvent.user_id)
            .filter(
                Song.artist_id == artist_id,
                *_valid_stream_filter_conditions(),
                ListeningEvent.created_at >= start_utc,
                ListeningEvent.created_at <= now_utc,
                ListeningEvent.user_id.isnot(None),
                ListeningEvent.user_id.in_(user_ids),
            )
            .group_by(ListeningEvent.user_id, Song.id, Song.title)
            .all()
        )

        # Per user: top song by streams DESC, song_id ASC (tie-break).
        best: dict[int, tuple[int, int, Optional[str]]] = {}
        for uid, song_id, title, stream_count in song_rows:
            uid_i = int(uid)
            sid_i = int(song_id)
            sc = int(stream_count)
            if uid_i not in best:
                best[uid_i] = (sc, sid_i, title)
            else:
                cur_sc, cur_sid, cur_title = best[uid_i]
                if sc > cur_sc or (sc == cur_sc and sid_i < cur_sid):
                    best[uid_i] = (sc, sid_i, title)

        out: List[dict] = []
        for user_id, username, valid_streams in step1:
            uid_i = int(user_id)
            raw_name = username
            if raw_name is None or str(raw_name).strip() == "":
                display_name = "Unknown user"
            else:
                display_name = str(raw_name).strip()

            top = best.get(uid_i)
            if top is None:
                top_sc, top_sid, top_title = 0, 0, ""
            else:
                top_sc, top_sid, top_title = top
            out.append(
                {
                    "user_id": uid_i,
                    "username": display_name,
                    "streams": int(valid_streams),
                    "top_song": {
                        "song_id": top_sid,
                        "title": top_title if top_title is not None else "",
                        "streams": top_sc,
                    },
                }
            )

        return out
    finally:
        db.close()


def _insight_display_username(raw: Optional[object]) -> str:
    if raw is None:
        return "Unknown user"
    s = str(raw).strip()
    return s if s else "Unknown user"


def get_artist_insights(
    artist_id: int,
    range: str = "last_30_days",
) -> Dict[str, Any]:
    """
    Fan storytelling insights from ListeningEvent (+ Song, User) only.

    Stream definition: economically valid listen; time on created_at (UTC).
    Up to 3 stories returned, sorted by priority (asc).
    """
    db = SessionLocal()
    stories: List[Dict[str, Any]] = []
    try:
        start_utc, now_utc = _resolve_utc_range(range)
        start_week, now_week = _resolve_utc_range("last_week")
        start_30, now_30 = _resolve_utc_range("last_30_days")

        song_count = (
            db.query(func.count(Song.id))
            .filter(Song.artist_id == artist_id)
            .scalar()
        )
        song_count = int(song_count or 0)

        if song_count == 0:
            stories.append(
                {
                    "type": "no_songs",
                    "priority": 1,
                    "message": "Upload your first song and start reaching listeners",
                    "data": {},
                }
            )

        total_valid_streams = (
            db.query(func.count(ListeningEvent.id))
            .join(Song, Song.id == ListeningEvent.song_id)
            .filter(
                Song.artist_id == artist_id,
                *_valid_stream_filter_conditions(),
            )
            .scalar()
        )
        total_valid_streams = int(total_valid_streams or 0)

        if song_count > 0 and total_valid_streams == 0:
            stories.append(
                {
                    "type": "no_streams",
                    "priority": 2,
                    "message": "Your music is ready. Now let's get your first listener",
                    "data": {},
                }
            )

        distinct_in_range = (
            db.query(func.count(distinct(ListeningEvent.user_id)))
            .select_from(ListeningEvent)
            .join(Song, Song.id == ListeningEvent.song_id)
            .filter(
                Song.artist_id == artist_id,
                *_valid_stream_filter_conditions(),
                ListeningEvent.created_at >= start_utc,
                ListeningEvent.created_at <= now_utc,
            )
            .scalar()
        )
        distinct_in_range = int(distinct_in_range or 0)

        if 1 <= distinct_in_range <= 2:
            stories.append(
                {
                    "type": "early_listeners",
                    "priority": 3,
                    "message": "You're starting to reach listeners 🎧",
                    "data": {"listeners": distinct_in_range},
                }
            )

        first_fan_row = (
            db.query(ListeningEvent.user_id, func.count(ListeningEvent.id).label("valid_streams"))
            .join(Song, Song.id == ListeningEvent.song_id)
            .filter(
                Song.artist_id == artist_id,
                *_valid_stream_filter_conditions(),
            )
            .group_by(ListeningEvent.user_id)
            .having(func.count(ListeningEvent.id) >= 2)
            .order_by(ListeningEvent.user_id.asc())
            .limit(1)
            .first()
        )
        if first_fan_row is not None:
            stories.append(
                {
                    "type": "first_fans",
                    "priority": 4,
                    "message": "Someone is coming back to your music — you're building your first fans",
                    "data": {"user_id": int(first_fan_row[0]), "streams": int(first_fan_row[1])},
                }
            )

        first_replay_row = (
            db.query(
                ListeningEvent.user_id,
                Song.id.label("song_id"),
                func.count(ListeningEvent.id).label("valid_streams"),
            )
            .join(Song, Song.id == ListeningEvent.song_id)
            .filter(
                Song.artist_id == artist_id,
                *_valid_stream_filter_conditions(),
            )
            .group_by(ListeningEvent.user_id, Song.id)
            .having(func.count(ListeningEvent.id) >= 2)
            .order_by(ListeningEvent.user_id.asc(), Song.id.asc())
            .limit(1)
            .first()
        )
        if first_replay_row is not None:
            stories.append(
                {
                    "type": "first_replays",
                    "priority": 5,
                    "message": "Your song is getting replayed 🔁",
                    "data": {
                        "user_id": int(first_replay_row[0]),
                        "song_id": int(first_replay_row[1]),
                        "streams": int(first_replay_row[2]),
                    },
                }
            )

        engagement_row = (
            db.query(
                ListeningEvent.user_id,
                func.max(User.username).label("username"),
                Song.id.label("song_id"),
                Song.title.label("song_title"),
                func.count(ListeningEvent.id).label("valid_streams"),
            )
            .join(Song, Song.id == ListeningEvent.song_id)
            .join(User, User.id == ListeningEvent.user_id)
            .filter(
                Song.artist_id == artist_id,
                *_valid_stream_filter_conditions(),
                ListeningEvent.created_at >= start_utc,
                ListeningEvent.created_at <= now_utc,
            )
            .group_by(ListeningEvent.user_id, Song.id, Song.title)
            .order_by(
                func.count(ListeningEvent.id).desc(),
                ListeningEvent.user_id.asc(),
                Song.id.asc(),
            )
            .limit(1)
            .first()
        )
        if engagement_row is not None:
            eng_streams = int(engagement_row[4])
            uname = _insight_display_username(engagement_row[1])
            stitle = engagement_row[3] if engagement_row[3] is not None else ""
            stories.append(
                {
                    "type": "fan_engagement",
                    "priority": 6,
                    "message": (
                        "Your fans are deeply engaged — one listener played your song "
                        f"{eng_streams} times"
                    ),
                    "data": {
                        "username": uname,
                        "song_title": stitle,
                        "streams": eng_streams,
                    },
                }
            )

        top_week_row = (
            db.query(
                ListeningEvent.user_id,
                func.max(User.username).label("username"),
                func.count(ListeningEvent.id).label("valid_streams"),
            )
            .join(Song, Song.id == ListeningEvent.song_id)
            .join(User, User.id == ListeningEvent.user_id)
            .filter(
                Song.artist_id == artist_id,
                *_valid_stream_filter_conditions(),
                ListeningEvent.created_at >= start_week,
                ListeningEvent.created_at <= now_week,
            )
            .group_by(ListeningEvent.user_id)
            .order_by(
                func.count(ListeningEvent.id).desc(),
                ListeningEvent.user_id.asc(),
            )
            .limit(1)
            .first()
        )
        if top_week_row is not None:
            tw_streams = int(top_week_row[2])
            uname = _insight_display_username(top_week_row[1])
            stories.append(
                {
                    "type": "top_fan_week",
                    "priority": 7,
                    "message": (
                        f"Your top fan listened {tw_streams} times in the last 7 days"
                    ),
                    "data": {"username": uname, "streams": tw_streams},
                }
            )

        listeners_30 = (
            db.query(func.count(distinct(ListeningEvent.user_id)))
            .select_from(ListeningEvent)
            .join(Song, Song.id == ListeningEvent.song_id)
            .filter(
                Song.artist_id == artist_id,
                *_valid_stream_filter_conditions(),
                ListeningEvent.created_at >= start_30,
                ListeningEvent.created_at <= now_30,
            )
            .scalar()
        )
        listeners_30 = int(listeners_30 or 0)

        if listeners_30 > 0:
            stories.append(
                {
                    "type": "fans_reached",
                    "priority": 8,
                    "message": (
                        f"Your music reached {listeners_30} listeners in the last 30 days"
                    ),
                    "data": {"listeners": listeners_30},
                }
            )

        stories.sort(key=lambda s: int(s["priority"]))
        top = stories[:3]

        return {"range": range, "stories": top}
    finally:
        db.close()
