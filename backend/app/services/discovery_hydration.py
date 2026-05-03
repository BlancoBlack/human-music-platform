"""
Discovery Step 4: batch hydration for /discovery/home.

Uses the same public URL rules as catalog endpoints (``media_urls.public_media_url_from_stored_path``).
"""

from __future__ import annotations

import logging
import time
from typing import Any

from sqlalchemy.orm import Session

from app.models.artist import Artist
from app.models.release_media_asset import (
    RELEASE_MEDIA_ASSET_TYPE_COVER_ART,
    ReleaseMediaAsset,
)
from app.models.song import Song
from app.models.song_media_asset import (
    SONG_MEDIA_KIND_MASTER_AUDIO,
    SongMediaAsset,
)
from app.services.discovery_row_normalize import (
    UNKNOWN_ARTIST,
    UNKNOWN_TRACK,
    normalize_discovery_track_row,
    normalize_discovery_sections_response,
)
from app.services.media_urls import public_media_url_from_stored_path

logger = logging.getLogger(__name__)

_MAX_HYDRATION_WARNINGS = 5

_SECTION_KEYS = ("play_now", "for_you", "explore", "curated")


def build_placeholder(song_id: int) -> dict:
    """Single source for missing / invalid song rows (pre-normalization shape)."""
    return {
        "id": int(song_id),
        "title": UNKNOWN_TRACK,
        "artist_name": UNKNOWN_ARTIST,
        "audio_url": None,
        "cover_url": None,
        "playable": False,
    }


def build_union_ids(sections: dict[str, list[int]]) -> list[int]:
    """First-seen order: play_now → for_you → explore → curated. Values coerced to int."""
    seen: set[int] = set()
    out: list[int] = []
    for key in _SECTION_KEYS:
        for raw in sections.get(key) or []:
            sid = int(raw)
            if sid in seen:
                continue
            seen.add(sid)
            out.append(sid)
    return out


def _warn(ctx: dict[str, Any], reason: str, song_id: int) -> None:
    if ctx["warn_count"] >= _MAX_HYDRATION_WARNINGS:
        ctx["warnings_truncated"] = True
        return
    ctx["warn_count"] += 1
    logger.warning(
        "discovery_hydration_issue",
        extra={
            "source": "discovery_home",
            "stage": "hydration",
            "reason": reason,
            "song_id": song_id,
        },
    )


def _valid_master_audio(asset: SongMediaAsset | None) -> bool:
    if asset is None:
        return False
    fp = asset.file_path
    if fp is None:
        return False
    return bool(str(fp).strip())


def _pick_master_assets(assets: list[SongMediaAsset]) -> dict[int, SongMediaAsset]:
    """First master-audio asset per song by minimum ``SongMediaAsset.id``."""
    masters: dict[int, SongMediaAsset] = {}
    for a in assets:
        if a.kind != SONG_MEDIA_KIND_MASTER_AUDIO:
            continue
        sid = int(a.song_id)
        cur = masters.get(sid)
        if cur is None or int(a.id) < int(cur.id):
            masters[sid] = a
    return masters


def _fetch_song_hydration_batch(
    db: Session,
    song_ids: list[int],
) -> tuple[
    dict[int, tuple[Song, str | None]],
    dict[int, SongMediaAsset],
    dict[int, str],
]:
    """
    Shared batched reads for discovery + playlist detail (no N+1).

    Cover raw paths match ``effective_song_cover`` semantics when ``Song.release_id``
    references an existing release with ``ReleaseMediaAsset`` COVER_ART (same selection
    rules as discovery; paths are turned into public URL paths via
    ``public_media_url_from_stored_path`` downstream).
    """
    song_rows = (
        db.query(Song, Artist.name)
        .outerjoin(Artist, Song.artist_id == Artist.id)
        .filter(Song.id.in_(song_ids), Song.deleted_at.is_(None))
        .all()
    )
    song_by_id: dict[int, tuple[Song, str | None]] = {}
    for song, artist_name in song_rows:
        song_by_id[int(song.id)] = (song, artist_name)

    asset_rows = (
        db.query(SongMediaAsset)
        .filter(
            SongMediaAsset.song_id.in_(song_ids),
            SongMediaAsset.kind == SONG_MEDIA_KIND_MASTER_AUDIO,
        )
        .all()
    )
    masters = _pick_master_assets(list(asset_rows))

    release_ids = {
        int(song.release_id)
        for song, _artist_name in song_rows
        if song.release_id is not None
    }
    release_cover_map: dict[int, str] = {}
    if release_ids:
        release_cover_rows = (
            db.query(ReleaseMediaAsset.release_id, ReleaseMediaAsset.file_path)
            .filter(
                ReleaseMediaAsset.release_id.in_(release_ids),
                ReleaseMediaAsset.asset_type == RELEASE_MEDIA_ASSET_TYPE_COVER_ART,
            )
            .all()
        )
        for release_id, file_path in release_cover_rows:
            rid = int(release_id)
            if rid in release_cover_map:
                continue
            if file_path is None:
                continue
            path = str(file_path).strip()
            if not path:
                continue
            release_cover_map[rid] = path

    return song_by_id, masters, release_cover_map


def _hydrate_catalog_track_normalized(
    sid: int,
    song: Song,
    artist_name: str | None,
    masters: dict[int, SongMediaAsset],
    release_cover_map: dict[int, str],
    *,
    warn_ctx: dict[str, Any] | None,
) -> dict:
    """Single-song hydration + ``normalize_discovery_track_row`` (discovery / playlists)."""
    title_raw = song.title
    title = str(title_raw).strip() if title_raw is not None else ""
    if not title:
        title = UNKNOWN_TRACK

    an = (str(artist_name).strip() if artist_name is not None else "") or UNKNOWN_ARTIST

    master = masters.get(sid)
    release_cover_path = None
    if song.release_id is not None:
        release_cover_path = release_cover_map.get(int(song.release_id))
    valid_master = _valid_master_audio(master)
    upload_ready = str(song.upload_status or "") == "ready"
    playable = bool(upload_ready and valid_master)

    if upload_ready and not valid_master and warn_ctx is not None:
        _warn(warn_ctx, "ready_without_valid_master", sid)

    audio_raw = public_media_url_from_stored_path(master.file_path if master else None)
    cover_raw = public_media_url_from_stored_path(release_cover_path)

    row = {
        "id": sid,
        "title": title,
        "artist_name": an,
        "audio_url": audio_raw,
        "cover_url": cover_raw,
        "playable": playable,
    }
    return normalize_discovery_track_row(row)


def hydrate_songs_batch_for_playlist(db: Session, song_ids: list[int]) -> dict[int, dict]:
    """
    Batch-hydrate songs for playlist detail responses.

    Same playable / ``audio_url`` / ``cover_url`` rules as discovery home hydration
    (via ``normalize_discovery_track_row``). Missing or soft-deleted songs yield a
    normalized placeholder row (no discovery warning logs).
    """
    out: dict[int, dict] = {}
    if not song_ids:
        return out
    unique_ids = list(dict.fromkeys(int(x) for x in song_ids))
    song_by_id, masters, release_cover_map = _fetch_song_hydration_batch(db, unique_ids)

    for sid in unique_ids:
        tup = song_by_id.get(sid)
        if tup is None:
            out[sid] = normalize_discovery_track_row(dict(build_placeholder(sid)))
            continue
        song, an = tup
        out[sid] = _hydrate_catalog_track_normalized(
            sid,
            song,
            an,
            masters,
            release_cover_map,
            warn_ctx=None,
        )

    return out


def hydrate_discovery_rows(db: Session, union_ids: list[int]) -> tuple[dict[int, dict], bool]:
    """
    Two queries (songs+artist, assets). ``hydrate_map`` keys follow ``union_ids`` order when filled.

    Iterate ``for sid in union_ids`` when building the map — never DB row order.

    Returns ``(hydrate_map, hydration_warnings_truncated)`` when warning logs were capped.
    """
    ctx: dict[str, Any] = {"warn_count": 0, "warnings_truncated": False}
    out: dict[int, dict] = {}

    if not union_ids:
        return out, False

    song_by_id, masters, release_cover_map = _fetch_song_hydration_batch(db, union_ids)

    for sid in union_ids:
        tup = song_by_id.get(sid)
        if tup is None:
            _warn(ctx, "missing_song", sid)
            out[sid] = normalize_discovery_track_row(dict(build_placeholder(sid)))
            continue

        song, artist_name = tup
        out[sid] = _hydrate_catalog_track_normalized(
            sid,
            song,
            artist_name,
            masters,
            release_cover_map,
            warn_ctx=ctx,
        )

    return out, bool(ctx.get("warnings_truncated"))


def assemble_discovery_response(
    sections: dict[str, list[int]],
    hydrate_map: dict[int, dict],
    *,
    context_by_song: dict[int, str | None] | None = None,
) -> dict[str, list[dict]]:
    """
    Section order is the source of truth. Hydration must never reorder items.

    Always appends ``dict(...)`` copies; never reuses the same dict instance.
    """
    if __debug__:
        seen: set[int] = set()
        for key in _SECTION_KEYS:
            for sid in sections.get(key) or []:
                i = int(sid)
                assert i not in seen, "duplicate song_id across discovery sections"
                seen.add(i)

    raw: dict[str, list[dict]] = {}
    for key in _SECTION_KEYS:
        block: list[dict] = []
        for sid in sections.get(key) or []:
            i = int(sid)
            base = hydrate_map.get(i)
            if base is None:
                base = build_placeholder(i)
            row = dict(base)
            if context_by_song is not None:
                row["context_tag"] = context_by_song.get(i)
            block.append(row)
        raw[key] = block

    return normalize_discovery_sections_response(raw)


def _discovery_home_response_metrics(
    response: dict[str, list[dict]],
) -> tuple[int, int, float, float, int]:
    """
    Aggregate-safe counts from the final normalized response.

    Returns:
        total_tracks_returned, unique_tracks, playable_ratio,
        non_playable_ratio, curated_count
    """
    total = 0
    non_playable = 0
    seen_ids: set[int] = set()
    for key in _SECTION_KEYS:
        for row in response.get(key) or []:
            total += 1
            seen_ids.add(int(row["id"]))
            if row.get("playable") is not True:
                non_playable += 1
    unique = len(seen_ids)
    curated_count = len(response.get("curated") or [])
    playable_ratio = (total - non_playable) / total if total else 0.0
    non_playable_ratio = non_playable / total if total else 0.0
    return total, unique, float(playable_ratio), float(non_playable_ratio), curated_count


def _log_discovery_home_observability(
    response: dict[str, list[dict]],
    *,
    anonymous: bool,
    hydration_warnings_truncated: bool,
    timings_ms: dict[str, float] | None,
) -> None:
    """One INFO summary + optional WARNING for high non-playable ratio (no PII)."""
    total, unique, playable_ratio, non_playable_ratio, curated_count = _discovery_home_response_metrics(
        response
    )

    extra_summary: dict[str, Any] = {
        "event": "discovery_home",
        "total_tracks_returned": total,
        "unique_tracks": unique,
        "playable_ratio": round(playable_ratio, 4),
        "curated_count": curated_count,
        "anonymous": bool(anonymous),
        "hydration_warnings_truncated": bool(hydration_warnings_truncated),
    }
    if timings_ms:
        for k, v in timings_ms.items():
            extra_summary[k] = round(float(v), 3) if isinstance(v, (int, float)) else v

    logger.info("discovery_home", extra=extra_summary)

    if total > 0 and non_playable_ratio > 0.5:
        logger.warning(
            "discovery_high_non_playable_ratio",
            extra={
                "event": "discovery_high_non_playable_ratio",
                "ratio": round(non_playable_ratio, 4),
                "total_tracks": total,
                "anonymous": bool(anonymous),
            },
        )


def build_discovery_home_sections(
    db: Session,
    sections: dict[str, list[int]],
    *,
    context_by_song: dict[int, str | None] | None = None,
    section_microcopy: dict[str, str] | None = None,
    anonymous: bool = False,
    timings_ms: dict[str, float] | None = None,
) -> dict[str, list[dict]]:
    """Union → hydrate (0 queries if empty) → assemble with strict normalization.

    Emits one structured INFO log per call (and optionally a WARNING for high non-playable ratio).
    ``anonymous`` / ``timings_ms`` are observability-only; they do not affect the returned payload.
    """
    union_ids = build_union_ids(sections)
    if not union_ids:
        empty = {k: [] for k in _SECTION_KEYS}
        response = normalize_discovery_sections_response(empty)
        if section_microcopy:
            response["section_microcopy"] = dict(section_microcopy)
        merged_ms: dict[str, float] = dict(timings_ms or {})
        merged_ms.setdefault("hydration_ms", 0.0)
        if "pool_ms" in merged_ms and "ranking_ms" in merged_ms:
            merged_ms["total_ms"] = round(
                float(merged_ms["pool_ms"])
                + float(merged_ms["ranking_ms"])
                + float(merged_ms["hydration_ms"]),
                3,
            )
        _log_discovery_home_observability(
            response,
            anonymous=anonymous,
            hydration_warnings_truncated=False,
            timings_ms=merged_ms,
        )
        return response

    t_hydrate = time.perf_counter()
    hydrate_map, warnings_truncated = hydrate_discovery_rows(db, union_ids)
    response = assemble_discovery_response(
        sections,
        hydrate_map,
        context_by_song=context_by_song,
    )
    if section_microcopy:
        response["section_microcopy"] = dict(section_microcopy)
    hydration_ms = (time.perf_counter() - t_hydrate) * 1000.0

    merged_ms = dict(timings_ms or {})
    merged_ms["hydration_ms"] = round(hydration_ms, 3)
    if "pool_ms" in merged_ms and "ranking_ms" in merged_ms:
        merged_ms["total_ms"] = round(
            float(merged_ms["pool_ms"]) + float(merged_ms["ranking_ms"]) + float(merged_ms["hydration_ms"]),
            3,
        )

    _log_discovery_home_observability(
        response,
        anonymous=anonymous,
        hydration_warnings_truncated=warnings_truncated,
        timings_ms=merged_ms,
    )
    return response
