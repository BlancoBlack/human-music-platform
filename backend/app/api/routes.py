import json
import logging
import math
import os
import threading
import time
from collections import deque
from decimal import Decimal
from datetime import date, datetime, timedelta
from typing import Annotated, Literal, Optional
from urllib.parse import quote, urlencode

from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, case, desc, func
from sqlalchemy.orm import joinedload

from app.api.deps import (
    enforce_participant_actor,
    enforce_artist_ownership,
    get_current_context,
    get_current_user,
    get_listening_user_id,
    is_context_allowed_for_user,
    require_admin_user,
    require_artist_owner,
    require_release_owner,
    require_non_impersonation,
    require_permission,
    require_self_or_admin,
    require_song_owner,
    validate_context_for_user_or_403,
)
from app.api.schemas.studio import (
    ApprovalActionResponse,
    PendingApprovalsListResponse,
    PendingApprovalsResponse,
    ReleaseDetailResponse,
)
from app.core.database import SessionLocal, get_db
from app.core.explorer_urls import lora_transaction_explorer_url
from app.data.genres import CANONICAL_GENRE_ORDER
from app.models.artist import Artist
from app.models.genre import Genre
from app.models.listening_event import ListeningEvent
from app.models.label import Label
from app.models.release import RELEASE_STATE_PUBLISHED, RELEASE_TYPE_ALBUM, Release
from app.models.release_participant import (
    RELEASE_PARTICIPANT_STATUS_ACCEPTED,
    RELEASE_PARTICIPANT_STATUS_PENDING,
    RELEASE_PARTICIPANT_STATUS_REJECTED,
    ReleaseParticipant,
)
from app.models.song_artist_split import SongArtistSplit
from app.models.release_media_asset import RELEASE_MEDIA_ASSET_TYPE_COVER_ART, ReleaseMediaAsset
from app.models.song import Song
from app.models.subgenre import Subgenre
from app.models.song_credit_entry import SongCreditEntry
from app.models.song_featured_artist import SongFeaturedArtist
from app.models.song_media_asset import (
    SONG_MEDIA_KIND_MASTER_AUDIO,
    SongMediaAsset,
)
from app.models.admin_action_log import AdminActionLog
from app.models.user import User
from app.services.media_urls import public_media_url_from_stored_path
from app.services.payout_batch_lock import BatchLockContentionError
from app.services.payout_service import calculate_user_distribution
from app.services.payout_ledger_ui_service import (
    fetch_admin_ledger_groups,
    synthetic_ledger_group_id,
)
from app.services.payout_aggregation_service import (
    get_artist_payout_capabilities,
    get_artist_payout_history,
    get_artist_payout_summary,
)
from app.services.artist_distribution_service import expand_song_distribution_to_artists
from app.services.pool_payout_service import calculate_global_distribution
from app.services.listening_checkpoint_service import (
    process_start_listening_session,
    process_stream_checkpoint,
)
from app.services.stream_service import StreamService
from app.services.comparison_service import compare_models
from app.services.artist_dashboard_service import get_artist_dashboard
from app.services.analytics_service import (
    get_artist_insights,
    get_artist_streams_over_time,
    get_artist_top_fans,
    get_artist_top_songs,
)
from app.services.song_artist_split_service import set_splits_for_song
from app.services.song_ingestion_service import SongIngestionService
from app.services.song_media_upload_service import (
    CoverResolutionInvalidError,
    MasterAudioImmutableError,
    WavFileTooLargeError,
    upload_release_cover_art,
    upload_song_master_audio,
)
from app.services.media_utils import effective_song_cover
from app.services.song_metadata_service import create_song_with_metadata, update_existing_song_metadata
from app.services.release_service import (
    create_release,
    get_release_progress,
    get_release_tracks,
    publish_release,
)
from app.services.release_participant_service import get_release_feature_artist_ids_map
from app.services.release_approval_service import (
    approve_participation,
    list_release_approvals,
    reject_participation,
)
from app.services.slug_service import (
    resolve_artist_slug,
    resolve_release_slug,
    resolve_song_slug,
)
from app.services.search_service import search_global
from app.services.song_split_validation import SplitValidationError
from app.workers.settlement_worker import (
    process_batch_settlement,
    retry_failed_settlements_for_batch,
)

logger = logging.getLogger(__name__)

router = APIRouter()

stream_service = StreamService()


def _next_app_base_url() -> str:
    return os.getenv("NEXT_APP_BASE_URL", "http://localhost:3000").rstrip("/")


def _artist_upload_href(artist_id: int) -> str:
    return f"{_next_app_base_url()}/artist-upload?artist_id={artist_id}"


def _artist_catalog_href(artist_id: int) -> str:
    return f"{_next_app_base_url()}/artist-catalog?artist_id={artist_id}"


def _artist_slug_href(slug: str) -> str:
    return f"{_next_app_base_url()}/artist/{quote(slug)}"


def _album_slug_href(slug: str) -> str:
    return f"{_next_app_base_url()}/album/{quote(slug)}"


def _track_slug_href(slug: str) -> str:
    return f"{_next_app_base_url()}/track/{quote(slug)}"


# Shared dark UI for artist HTML pages (dashboard / payouts).
_ARTIST_HUB_CSS = """
*, *::before, *::after { box-sizing: border-box; }
body.artist-hub {
  margin: 0;
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  background: #0a0a0a;
  color: #fafafa;
  line-height: 1.5;
  min-height: 100vh;
  -webkit-font-smoothing: antialiased;
}
.artist-hub-inner {
  max-width: 56rem;
  margin: 0 auto;
  padding: 2rem 1.25rem 4rem;
}
.artist-hub h1 {
  font-size: 1.5rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  margin: 0 0 0.5rem 0;
}
.artist-hub-nav {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem 0.5rem;
  padding-bottom: 0.75rem;
  margin-bottom: 1.5rem;
  border-bottom: 1px solid #27272a;
}
.artist-hub-nav a {
  color: #a1a1aa;
  text-decoration: none;
  font-size: 0.875rem;
  transition: color 0.15s ease;
}
.artist-hub-nav a:hover { color: #fafafa; }
.artist-hub-nav a.is-active {
  color: #fafafa;
  font-weight: 700;
}
.artist-hub-nav .sep {
  color: #3f3f46;
  user-select: none;
  font-weight: 300;
}
.ah-card {
  background: #18181b;
  border: 1px solid #27272a;
  border-radius: 0.75rem;
  padding: 1.25rem 1.5rem;
  margin-bottom: 1.5rem;
}
.ah-card h2 {
  margin-top: 0;
  font-size: 1.125rem;
  font-weight: 600;
  color: #fafafa;
}
.ah-card h3 {
  font-size: 1rem;
  font-weight: 600;
  color: #fafafa;
}
.ah-card p, .artist-hub section p { color: #d4d4d8; }
.ah-card .ah-lead, .artist-hub .ah-lead {
  color: #a1a1aa;
  font-size: 0.875rem;
  margin-bottom: 1rem;
}
.ah-card--earnings { border-color: #3f3f46; }
.ah-card--accent {
  border-color: rgba(34, 197, 94, 0.35);
  background: linear-gradient(180deg, #14532d12 0%, #18181b 100%);
}
.ah-card--compare { border-color: rgba(59, 130, 246, 0.35); }
.ah-card--payout { border-color: rgba(245, 158, 11, 0.35); }
.ah-card--hero {
  border-color: rgba(251, 146, 60, 0.35);
  background: linear-gradient(180deg, #7c2d1218 0%, #18181b 100%);
}
.ah-muted { color: #a1a1aa !important; }
.ah-code {
  font-family: ui-monospace, monospace;
  font-size: 0.85em;
  background: #27272a;
  padding: 0.125rem 0.375rem;
  border-radius: 0.25rem;
  color: #e4e4e7;
}
.artist-hub code { font-family: ui-monospace, monospace; font-size: 0.85em; background: #27272a; padding: 0.125rem 0.375rem; border-radius: 0.25rem; color: #e4e4e7; }
.artist-hub a.ah-inline-link { color: #93c5fd; text-decoration: none; }
.artist-hub a.ah-inline-link:hover { text-decoration: underline; }
.ah-btn {
  margin-top: 0.75rem;
  padding: 0.5rem 1rem;
  font-size: 0.875rem;
  font-weight: 500;
  color: #fafafa;
  background: #27272a;
  border: 1px solid #3f3f46;
  border-radius: 0.5rem;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease;
}
.ah-btn:hover {
  background: #3f3f46;
  border-color: #52525b;
}
.ah-toggle-panel {
  display: none;
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid #27272a;
}
table.ah-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
  margin-top: 0.5rem;
}
table.ah-table th {
  text-align: left;
  padding: 0.65rem 0.75rem;
  border-bottom: 1px solid #3f3f46;
  color: #a1a1aa;
  font-weight: 600;
}
table.ah-table td {
  padding: 0.65rem 0.75rem;
  border-bottom: 1px solid #27272a;
  color: #e4e4e7;
}
table.ah-table tbody tr { transition: background 0.12s ease; }
table.ah-table tbody tr:hover { background: #27272a; }
table.ah-table-fixed { table-layout: fixed; }
.artist-hub label { color: #a1a1aa; font-size: 0.875rem; }
.artist-hub select, .artist-hub input[type="text"], .artist-hub textarea {
  background: #09090b;
  color: #fafafa;
  border: 1px solid #3f3f46;
  border-radius: 0.5rem;
  padding: 0.5rem 0.65rem;
  font-size: 0.875rem;
}
.artist-hub select:focus, .artist-hub input:focus, .artist-hub textarea:focus {
  outline: none;
  border-color: #71717a;
}
.ah-form-actions { margin-bottom: 0; margin-top: 0.5rem; }
.ah-payout-row td:last-child { color: #a1a1aa; font-size: 0.8rem; }
#heroInsight { display: none; }
.ah-hero-title { margin-top: 0; }
.ah-hero-msg { font-size: 1.1rem; margin: 0.5rem 0; line-height: 1.5; color: #fafafa; }
.ah-hero-sub { font-size: 0.9rem; color: #a1a1aa; margin-top: 0.75rem; margin-bottom: 0; }
.ah-warn { color: #fbbf24; }
.artist-hub b { color: #fafafa; font-weight: 600; }
"""


def _artist_hub_html_head(page_title: str, *, extra_head: str = "") -> str:
    esc = _html_escape(page_title)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{esc}</title>
<style>
{_ARTIST_HUB_CSS}
</style>
{extra_head}
</head>
"""


def _artist_hub_nav(artist_id: int, active: str) -> str:
    """active: overview | analytics | payouts (payouts href is Next Studio; no legacy HTML page)."""
    studio_payouts = f"{_next_app_base_url()}/studio/payouts"
    studio_analytics = f"{_next_app_base_url()}/studio/analytics"
    items: list[tuple[str, str, str]] = [
        ("overview", f"/artist-dashboard/{artist_id}", "Overview"),
        ("analytics", studio_analytics, "Analytics"),
        ("payouts", studio_payouts, "Payouts"),
        ("upload", _artist_upload_href(artist_id), "Upload"),
        ("catalog", _artist_catalog_href(artist_id), "Catalog"),
    ]
    links: list[str] = []
    for key, href, label in items:
        if key == active:
            links.append(f'<a href="{href}" class="is-active">{label}</a>')
        else:
            links.append(f'<a href="{href}">{label}</a>')
    inner = '<span class="sep" aria-hidden="true">|</span>'.join(links)
    return f'<nav class="artist-hub-nav" aria-label="Artist hub">{inner}</nav>'


MAX_PAYOUT_TEXT_LEN = 255
ALLOWED_PAYOUT_METHODS = frozenset({"none", "crypto", "bank"})

# POST /stream only: in-memory sliding-window limits (single-process).
rate_limit_lock = threading.Lock()
_stream_rate_limit_store: dict[str, deque[float]] = {}
_STREAM_RL_IP_WINDOW_S = 60.0
_STREAM_RL_IP_MAX = 60
_STREAM_RL_USER_WINDOW_S = 60.0
_STREAM_RL_USER_MAX = 30
_STREAM_RL_BURST_WINDOW_S = 2.0
_STREAM_RL_BURST_MAX = 5
_TRUST_X_FORWARDED_FOR = os.getenv("TRUST_X_FORWARDED_FOR", "").strip().lower() == "true"

# POST /stream/checkpoint: separate limits (do not share /stream counters).
_checkpoint_rate_limit_store: dict[str, deque[float]] = {}
_CHECKPOINT_RL_USER_WINDOW_S = 60.0
_CHECKPOINT_RL_USER_MAX = 120

# POST /stream/start-session: limit idle session creation abuse.
_start_session_rate_limit_store: dict[str, deque[float]] = {}
_START_SESSION_RL_USER_WINDOW_S = 60.0
_START_SESSION_RL_USER_MAX = 30


def get_client_ip(request: Request) -> str:
    if _TRUST_X_FORWARDED_FOR:
        xff = request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For")
        if xff:
            first = xff.split(",")[0].strip()
            if first:
                return first
    if request.client is not None and request.client.host:
        return request.client.host
    return "unknown"


def _stream_rate_limit_prune(dq: deque[float], now: float, window_s: float) -> None:
    cutoff = now - window_s
    while dq and dq[0] < cutoff:
        dq.popleft()


def _stream_rate_limit_retry_after_s(dq: deque[float], now: float, window_s: float) -> float:
    if not dq:
        return 1.0
    return max(1.0, dq[0] + window_s - now)


def _rate_limit_get_pruned(
    store: dict[str, deque[float]], key: str, now: float, window_s: float
) -> deque[float]:
    dq = store.get(key)
    if dq is None:
        return deque()
    _stream_rate_limit_prune(dq, now, window_s)
    if not dq:
        del store[key]
        return deque()
    return dq


def _stream_rate_limit_get_pruned(key: str, now: float, window_s: float) -> deque[float]:
    return _rate_limit_get_pruned(_stream_rate_limit_store, key, now, window_s)


def _enforce_stream_rate_limit(request: Request, user_id: int) -> None:
    path = request.url.path
    if path.startswith("/dev/") or path.startswith("/admin/"):
        return

    client_ip = get_client_ip(request)
    ip_key = f"ip:{client_ip}"
    user_key = f"user:{user_id}"
    burst_key = f"burst:user:{user_id}"

    with rate_limit_lock:
        now = time.time()

        ip_dq = _stream_rate_limit_get_pruned(ip_key, now, _STREAM_RL_IP_WINDOW_S)
        user_dq = _stream_rate_limit_get_pruned(user_key, now, _STREAM_RL_USER_WINDOW_S)
        burst_dq = _stream_rate_limit_get_pruned(burst_key, now, _STREAM_RL_BURST_WINDOW_S)

        reason: str | None = None
        retry_after_s = 1.0
        if len(ip_dq) >= _STREAM_RL_IP_MAX:
            reason = "ip_rate_limited"
            retry_after_s = _stream_rate_limit_retry_after_s(
                ip_dq, now, _STREAM_RL_IP_WINDOW_S
            )
        elif len(user_dq) >= _STREAM_RL_USER_MAX:
            reason = "user_rate_limited"
            retry_after_s = _stream_rate_limit_retry_after_s(
                user_dq, now, _STREAM_RL_USER_WINDOW_S
            )
        elif len(burst_dq) >= _STREAM_RL_BURST_MAX:
            reason = "burst_rate_limited"
            retry_after_s = _stream_rate_limit_retry_after_s(
                burst_dq, now, _STREAM_RL_BURST_WINDOW_S
            )

        if reason is not None:
            logger.warning(
                "rate_limit_exceeded",
                extra={
                    "user_id": user_id,
                    "ip": client_ip,
                    "reason": reason,
                },
            )
            ra_int = max(1, int(math.ceil(retry_after_s)))
            raise HTTPException(
                status_code=429,
                detail={"status": "rate_limited", "reason": reason},
                headers={"Retry-After": str(ra_int)},
            )

        _stream_rate_limit_store[ip_key] = ip_dq
        _stream_rate_limit_store[user_key] = user_dq
        _stream_rate_limit_store[burst_key] = burst_dq
        ip_dq.append(now)
        user_dq.append(now)
        burst_dq.append(now)


def _enforce_checkpoint_rate_limit(request: Request, user_id: int) -> None:
    """Sliding window: max checkpoints per user per minute (separate from /stream)."""
    path = request.url.path
    if path.startswith("/dev/") or path.startswith("/admin/"):
        return

    user_key = f"checkpoint:user:{user_id}"
    with rate_limit_lock:
        now = time.time()
        dq = _rate_limit_get_pruned(
            _checkpoint_rate_limit_store, user_key, now, _CHECKPOINT_RL_USER_WINDOW_S
        )
        if len(dq) >= _CHECKPOINT_RL_USER_MAX:
            retry_after_s = _stream_rate_limit_retry_after_s(
                dq, now, _CHECKPOINT_RL_USER_WINDOW_S
            )
            logger.warning(
                "checkpoint_rate_limit_exceeded",
                extra={"user_id": user_id, "reason": "checkpoint_user_rate_limited"},
            )
            ra_int = max(1, int(math.ceil(retry_after_s)))
            raise HTTPException(
                status_code=429,
                detail={"status": "rate_limited", "reason": "checkpoint_user_rate_limited"},
                headers={"Retry-After": str(ra_int)},
            )
        _checkpoint_rate_limit_store[user_key] = dq
        dq.append(now)


def _enforce_start_session_rate_limit(request: Request, user_id: int) -> None:
    """Sliding window: max new listening sessions per user per minute."""
    path = request.url.path
    if path.startswith("/dev/") or path.startswith("/admin/"):
        return

    user_key = f"start_session:user:{user_id}"
    with rate_limit_lock:
        now = time.time()
        dq = _rate_limit_get_pruned(
            _start_session_rate_limit_store, user_key, now, _START_SESSION_RL_USER_WINDOW_S
        )
        if len(dq) >= _START_SESSION_RL_USER_MAX:
            retry_after_s = _stream_rate_limit_retry_after_s(
                dq, now, _START_SESSION_RL_USER_WINDOW_S
            )
            logger.warning(
                "start_session_rate_limit_exceeded",
                extra={"user_id": user_id, "reason": "start_session_user_rate_limited"},
            )
            ra_int = max(1, int(math.ceil(retry_after_s)))
            raise HTTPException(
                status_code=429,
                detail={"status": "rate_limited", "reason": "start_session_user_rate_limited"},
                headers={"Retry-After": str(ra_int)},
            )
        _start_session_rate_limit_store[user_key] = dq
        dq.append(now)


def require_dev_mode() -> None:
    env = (os.getenv("APP_ENV") or os.getenv("ENV") or "").strip().lower()
    allowed_envs = {"dev", "development", "local", "test"}
    enable_dev = (os.getenv("ENABLE_DEV_ENDPOINTS", "").strip().lower() == "true")
    if env in allowed_envs or enable_dev:
        return
    logger.warning(
        "dev_mode_check_denied",
        extra={
            "APP_ENV": os.getenv("APP_ENV"),
            "ENV": os.getenv("ENV"),
            "ENABLE_DEV_ENDPOINTS": os.getenv("ENABLE_DEV_ENDPOINTS"),
            "normalized_env": env,
        },
    )
    raise HTTPException(
        status_code=403,
        detail="Dev endpoint not allowed in this environment",
    )


def _html_escape(text: object) -> str:
    s = "" if text is None else str(text)
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _get_public_artist_or_404(db, artist_id: int) -> Artist:
    artist = db.query(Artist).filter(Artist.id == artist_id).first()
    if artist is None:
        raise HTTPException(status_code=404, detail="Artist not found")
    if bool(getattr(artist, "is_system", False)):
        raise HTTPException(status_code=404, detail="Artist not found")
    return artist


class SongSplitRowBody(BaseModel):
    artist_id: int = Field(..., description="Artist receiving this share")
    share: float = Field(..., description="Portion in (0, 1]; all rows must sum to 1.0")


class SetSongSplitsBody(BaseModel):
    splits: list[SongSplitRowBody] = Field(
        ...,
        min_length=1,
        description="Full replacement set of splits for the song",
    )


SongCreditRole = Literal[
    "songwriter",
    "composer",
    "arranger",
    "producer",
    "musician",
    "sound designer",
    "mix engineer",
    "mastering engineer",
    "artwork",
    "studio",
]


class CreateSongCreditBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=512)
    role: SongCreditRole


class CreateSongBody(BaseModel):
    title: str = Field(..., min_length=1)
    artist_id: int = Field(..., description="Primary (release) artist")
    release_id: int | None = Field(default=None, description="Existing release to attach song to")
    featured_artist_ids: list[int] = Field(default_factory=list, max_length=20)
    credits: list[CreateSongCreditBody] = Field(default_factory=list, max_length=20)
    genre_id: int | None = Field(default=None, ge=1)
    subgenre_id: int | None = Field(default=None, ge=1)
    moods: list[str] | None = Field(default=None, description="Optional mood tags")
    country_code: str | None = Field(
        default=None,
        max_length=2,
        description="ISO 3166-1 alpha-2 country code",
    )
    city: str | None = Field(default=None, max_length=128)


class PatchSongBody(BaseModel):
    """Full metadata snapshot for ``PATCH /songs/{id}`` (wizard / catalog edit)."""

    title: str = Field(..., min_length=1)
    artist_id: int = Field(..., ge=1, description="Must match the song's primary artist_id")
    featured_artist_ids: list[int] = Field(default_factory=list, max_length=20)
    credits: list[CreateSongCreditBody] = Field(default_factory=list, max_length=20)
    genre_id: int | None = Field(default=None, ge=1)
    subgenre_id: int | None = Field(default=None, ge=1)
    moods: list[str] | None = Field(default=None, description="Optional mood tags")
    country_code: str | None = Field(
        default=None,
        max_length=2,
        description="ISO 3166-1 alpha-2 country code",
    )
    city: str | None = Field(default=None, max_length=128)


class CreateReleaseBody(BaseModel):
    title: str = Field(..., min_length=1)
    artist_id: int = Field(..., ge=1)
    release_type: Literal["single", "album"] = Field(default="album")
    release_date: str = Field(
        ...,
        description="ISO 8601 datetime (e.g. 2026-04-13T12:00:00)",
    )


class ReleaseApprovalActionBody(BaseModel):
    artist_id: int = Field(..., ge=1)
    reason: str | None = Field(default=None, max_length=1000)


class StudioContextBody(BaseModel):
    type: Literal["user", "artist", "label"]
    id: int = Field(..., ge=1)


def _build_release_decision_payloads(
    *,
    db,
    release_ids: list[int],
    owned_artist_ids: set[int],
) -> dict[int, dict]:
    if not release_ids:
        return {}

    release_rows = (
        db.query(
            Release.id,
            Release.title,
            Release.approval_status,
            Release.split_version,
            Release.type,
            Release.created_at,
            Release.updated_at,
            Release.artist_id,
            Artist.name.label("release_artist_name"),
        )
        .join(Artist, Artist.id == Release.artist_id)
        .filter(Release.id.in_(release_ids))
        .all()
    )
    grouped: dict[int, dict] = {}
    for row in release_rows:
        release_id = int(row.id)
        grouped[release_id] = {
            "release": {
                "id": release_id,
                "title": row.title,
                "cover_url": None,
                "artist": {
                    "id": int(row.artist_id),
                    "name": row.release_artist_name,
                },
                "type": row.type,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "split_version": int(row.split_version or 1),
                "track_count": 0,
                "genres": [],
                "moods": [],
                "location": None,
            },
            "approval_status": row.approval_status,
            "songs": [],
            "splits": [],
            "participants": [],
            "pending_summary": {"split": 0, "feature": 0},
            "_updated_at": row.updated_at,
            "_created_at": row.created_at,
        }

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
        if rid in grouped and grouped[rid]["release"]["cover_url"] is None:
            grouped[rid]["release"]["cover_url"] = public_media_url_from_stored_path(file_path)

    song_rows = (
        db.query(
            Song.id,
            Song.release_id,
            Song.title,
            Song.artist_id,
            Genre.name.label("genre_name"),
            Song.moods,
            Song.country_code,
            Song.city,
        )
        .outerjoin(Genre, Genre.id == Song.genre_id)
        .filter(Song.release_id.in_(release_ids), Song.deleted_at.is_(None))
        .order_by(Song.release_id.asc(), Song.id.asc())
        .all()
    )
    song_ids: list[int] = []
    song_payload_by_id: dict[int, dict] = {}
    song_release_id_by_song_id: dict[int, int] = {}
    release_genres: dict[int, set[str]] = {rid: set() for rid in release_ids}
    release_moods: dict[int, set[str]] = {rid: set() for rid in release_ids}
    featured_artist_ids_by_release = get_release_feature_artist_ids_map(
        db,
        release_ids=release_ids,
    )
    for row in song_rows:
        release_id = int(row.release_id)
        if release_id not in grouped:
            continue
        song_id = int(row.id)
        song_ids.append(song_id)
        song_release_id_by_song_id[song_id] = release_id
        payload = {
            "id": song_id,
            "title": row.title,
            "primary_artist_id": int(row.artist_id),
            "featured_artists": [],
            "credits": [],
        }
        song_payload_by_id[song_id] = payload
        grouped[release_id]["songs"].append(payload)
        grouped[release_id]["release"]["track_count"] += 1
        if row.genre_name:
            release_genres[release_id].add(str(row.genre_name))
        for mood in (row.moods or []):
            release_moods[release_id].add(str(mood))
        if grouped[release_id]["release"]["location"] is None:
            if row.city and row.country_code:
                grouped[release_id]["release"]["location"] = f"{row.city}, {row.country_code}"
            elif row.city:
                grouped[release_id]["release"]["location"] = str(row.city)
            elif row.country_code:
                grouped[release_id]["release"]["location"] = str(row.country_code)

    if song_ids:
        featured_rows = (
            db.query(
                SongFeaturedArtist.song_id,
                SongFeaturedArtist.artist_id,
                Artist.name,
            )
            .join(Artist, Artist.id == SongFeaturedArtist.artist_id)
            .filter(SongFeaturedArtist.song_id.in_(song_ids))
            .order_by(SongFeaturedArtist.song_id.asc(), SongFeaturedArtist.position.asc())
            .all()
        )
        for row in featured_rows:
            song_payload = song_payload_by_id.get(int(row.song_id))
            if song_payload is not None:
                song_payload["featured_artists"].append(
                    {"artist_id": int(row.artist_id), "artist_name": row.name}
                )
            release_id = song_release_id_by_song_id.get(int(row.song_id))
            if release_id is not None and release_id not in featured_artist_ids_by_release:
                featured_artist_ids_by_release[release_id] = set()

        credit_rows = (
            db.query(
                SongCreditEntry.song_id,
                SongCreditEntry.display_name,
                SongCreditEntry.role,
            )
            .filter(SongCreditEntry.song_id.in_(song_ids))
            .order_by(SongCreditEntry.song_id.asc(), SongCreditEntry.position.asc())
            .all()
        )
        for row in credit_rows:
            song_payload = song_payload_by_id.get(int(row.song_id))
            if song_payload is not None:
                song_payload["credits"].append(
                    {"name": row.display_name, "role": row.role}
                )

        split_rows = (
            db.query(
                Song.release_id,
                SongArtistSplit.artist_id,
                Artist.name,
                func.sum(SongArtistSplit.split_bps).label("sum_split_bps"),
            )
            .join(Song, Song.id == SongArtistSplit.song_id)
            .join(Artist, Artist.id == SongArtistSplit.artist_id)
            .filter(Song.release_id.in_(release_ids), Song.deleted_at.is_(None))
            .group_by(Song.release_id, SongArtistSplit.artist_id, Artist.name)
            .all()
        )
        total_bps_by_release: dict[int, int] = {rid: 0 for rid in release_ids}
        split_payload_rows: dict[int, list[dict]] = {rid: [] for rid in release_ids}
        for row in split_rows:
            rid = int(row.release_id)
            bps = int(row.sum_split_bps or 0)
            total_bps_by_release[rid] += bps
            split_payload_rows[rid].append(
                {
                    "artist_id": int(row.artist_id),
                    "artist_name": row.name,
                    "_split_bps": bps,
                }
            )
        for rid in release_ids:
            if rid not in grouped:
                continue
            total = int(total_bps_by_release.get(rid, 0))
            payload = []
            for row in split_payload_rows.get(rid, []):
                share = (float(row["_split_bps"]) / float(total)) if total > 0 else 0.0
                payload.append(
                    {
                        "artist_id": row["artist_id"],
                        "artist_name": row["artist_name"],
                        "share": share,
                    }
                )
            grouped[rid]["splits"] = sorted(payload, key=lambda x: int(x["artist_id"]))

    for rid in release_ids:
        if rid not in grouped:
            continue
        grouped[rid]["release"]["genres"] = sorted(release_genres.get(rid, set()))
        grouped[rid]["release"]["moods"] = sorted(release_moods.get(rid, set()))

    participant_rows = (
        db.query(
            ReleaseParticipant.release_id,
            ReleaseParticipant.artist_id,
            Artist.name.label("artist_name"),
            ReleaseParticipant.role,
            ReleaseParticipant.status,
            ReleaseParticipant.approval_type,
            ReleaseParticipant.requires_approval,
            ReleaseParticipant.rejection_reason,
            ReleaseParticipant.approved_at,
        )
        .join(Artist, Artist.id == ReleaseParticipant.artist_id)
        .filter(ReleaseParticipant.release_id.in_(release_ids))
        .order_by(ReleaseParticipant.release_id.asc(), ReleaseParticipant.artist_id.asc())
        .all()
    )
    for row in participant_rows:
        rid = int(row.release_id)
        if rid not in grouped:
            continue
        approval_type = str(row.approval_type)
        is_actionable_for_user = (
            int(row.artist_id) in owned_artist_ids
            and bool(row.requires_approval)
            and str(row.status) == RELEASE_PARTICIPANT_STATUS_PENDING
        )
        participant_payload = {
            "artist_id": int(row.artist_id),
            "artist_name": row.artist_name,
            "role": row.role,
            "status": row.status,
            "approval_type": approval_type,
            "requires_approval": bool(row.requires_approval),
            "blocking": approval_type == "split",
            "is_actionable_for_user": is_actionable_for_user,
            "has_feature_context": int(row.artist_id) in featured_artist_ids_by_release.get(rid, set()),
            "rejection_reason": row.rejection_reason,
            "approved_at": row.approved_at.isoformat() if row.approved_at else None,
        }
        grouped[rid]["participants"].append(participant_payload)
        if is_actionable_for_user:
            if approval_type == "split":
                grouped[rid]["pending_summary"]["split"] += 1
            elif approval_type == "feature":
                grouped[rid]["pending_summary"]["feature"] += 1

    def _participant_sort_key(item: dict) -> tuple[int, int]:
        status = str(item.get("status", ""))
        approval_type = str(item.get("approval_type", ""))
        if status == RELEASE_PARTICIPANT_STATUS_PENDING and approval_type == "split":
            return (0, int(item.get("artist_id", 0)))
        if status == RELEASE_PARTICIPANT_STATUS_PENDING and approval_type == "feature":
            return (1, int(item.get("artist_id", 0)))
        if status == RELEASE_PARTICIPANT_STATUS_ACCEPTED:
            return (2, int(item.get("artist_id", 0)))
        if status == RELEASE_PARTICIPANT_STATUS_REJECTED:
            return (3, int(item.get("artist_id", 0)))
        return (4, int(item.get("artist_id", 0)))

    for rid in release_ids:
        if rid not in grouped:
            continue
        grouped[rid]["participants"] = sorted(
            grouped[rid]["participants"],
            key=_participant_sort_key,
        )
    return grouped


def _require_owner_for_create_song(
    body: CreateSongBody,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
) -> Artist:
    return enforce_artist_ownership(
        artist_id=int(body.artist_id),
        user=user,
        db=db,
    )


def _require_owner_for_create_release(
    body: CreateReleaseBody,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
) -> Artist:
    return enforce_artist_ownership(
        artist_id=int(body.artist_id),
        user=user,
        db=db,
    )


def _require_participant_actor_for_release_approval_action(
    release_id: int,
    body: ReleaseApprovalActionBody,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
) -> object:
    return enforce_participant_actor(
        release_id=int(release_id),
        artist_id=int(body.artist_id),
        user=user,
        db=db,
    )


@router.get("/studio/me")
def get_studio_me(
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    owned_artists = (
        db.query(Artist)
        .filter(Artist.owner_user_id == int(user.id))
        .order_by(Artist.id.asc())
        .all()
    )
    owned_labels = (
        db.query(Label)
        .filter(Label.owner_user_id == int(user.id))
        .order_by(Label.id.asc())
        .all()
    )
    current_context = get_current_context(db=db, user=user)
    allowed_contexts = {
        "artists": [
            {
                "id": int(artist.id),
                "name": artist.name,
                "slug": artist.slug,
            }
            for artist in owned_artists
        ],
        "labels": [
            {
                "id": int(label.id),
                "name": label.name,
            }
            for label in owned_labels
        ],
    }
    user_context = {
        "id": int(user.id),
        "email": user.email,
    }
    return {
        "user": user_context,
        "allowed_contexts": allowed_contexts,
        "current_context": current_context,
    }


def _get_first_tracks_for_releases(db, release_ids: list[int]) -> dict[int, Song]:
    """First ready song per release (album order), one SQL round-trip via ROW_NUMBER."""
    if not release_ids:
        return {}
    song_rank_subq = (
        db.query(
            Song.id.label("song_id"),
            func.row_number()
            .over(
                partition_by=Song.release_id,
                order_by=(
                    Song.track_number.is_(None).asc(),
                    Song.track_number.asc(),
                    Song.id.asc(),
                ),
            )
            .label("rn"),
        )
        .filter(
            Song.release_id.in_(release_ids),
            Song.deleted_at.is_(None),
            Song.upload_status == "ready",
        )
        .subquery()
    )
    first_songs = (
        db.query(Song)
        .join(
            song_rank_subq,
            and_(Song.id == song_rank_subq.c.song_id, song_rank_subq.c.rn == 1),
        )
        .all()
    )
    out: dict[int, Song] = {}
    for s in first_songs:
        rid = int(s.release_id) if s.release_id is not None else None
        if rid is not None:
            out[rid] = s
    return out


@router.get("/studio/{artist_id}/catalog")
def get_studio_catalog(
    artist_id: int,
    sort: Literal["top", "new", "old"] = Query(default="top"),
    _owned_artist: Artist = Depends(require_artist_owner),
    db=Depends(get_db),
):
    release_rows = (
        db.query(Release)
        .filter(
            Release.artist_id == int(artist_id),
            Release.state == RELEASE_STATE_PUBLISHED,
        )
        .order_by(
            case(
                (
                    Release.state == RELEASE_STATE_PUBLISHED,
                    func.coalesce(Release.discoverable_at, Release.created_at),
                ),
                else_=Release.discoverable_at,
            ).desc()
        )
        .limit(5)
        .all()
    )

    release_ids = [int(r.id) for r in release_rows]
    cover_rows = []
    if release_ids:
        cover_rows = (
            db.query(ReleaseMediaAsset.release_id, ReleaseMediaAsset.file_path)
            .filter(
                ReleaseMediaAsset.release_id.in_(release_ids),
                ReleaseMediaAsset.asset_type == RELEASE_MEDIA_ASSET_TYPE_COVER_ART,
            )
            .all()
        )
    release_cover_map: dict[int, str] = {}
    for release_id, file_path in cover_rows:
        rid = int(release_id)
        if rid in release_cover_map:
            continue
        if file_path is None:
            continue
        path = str(file_path).strip()
        if not path:
            continue
        release_cover_map[rid] = path

    artist = _get_public_artist_or_404(db, int(artist_id))

    first_song_by_release = _get_first_tracks_for_releases(db, release_ids)

    first_song_ids = [int(s.id) for s in first_song_by_release.values()]
    first_master_map: dict[int, SongMediaAsset] = {}
    if first_song_ids:
        for asset in (
            db.query(SongMediaAsset)
            .filter(
                SongMediaAsset.song_id.in_(first_song_ids),
                SongMediaAsset.kind == SONG_MEDIA_KIND_MASTER_AUDIO,
            )
            .all()
        ):
            sid = int(asset.song_id)
            if asset.kind == SONG_MEDIA_KIND_MASTER_AUDIO and sid not in first_master_map:
                first_master_map[sid] = asset

    releases_payload: list[dict] = []
    for release in release_rows:
        rid = int(release.id)
        rel_cover = public_media_url_from_stored_path(release_cover_map.get(rid))
        song = first_song_by_release.get(rid)
        first_track_payload = None
        if song is not None:
            sid = int(song.id)
            master = first_master_map.get(sid)
            track_cover_url = rel_cover
            first_track_payload = {
                "id": sid,
                "slug": song.slug,
                "title": song.title,
                "artist_name": artist.name,
                "duration_seconds": song.duration_seconds,
                "release_date": release.release_date.isoformat()
                if release.release_date
                else None,
                "stream_count": 0,
                "cover_url": track_cover_url,
                "audio_url": public_media_url_from_stored_path(
                    master.file_path if master else None
                ),
                "playable": bool(master is not None),
            }
        releases_payload.append(
            {
                "id": rid,
                "slug": release.slug,
                "title": release.title,
                "type": release.type,
                "release_date": release.release_date.isoformat()
                if release.release_date
                else None,
                "cover_url": rel_cover,
                "first_track": first_track_payload,
            }
        )

    stream_counts_subq = (
        db.query(
            ListeningEvent.song_id.label("song_id"),
            func.count(ListeningEvent.id).label("stream_count"),
        )
        .filter(
            ListeningEvent.is_valid.is_(True),
            ListeningEvent.validated_duration > 0,
        )
        .group_by(ListeningEvent.song_id)
        .subquery()
    )

    track_query = (
        db.query(
            Song,
            Release,
            func.coalesce(stream_counts_subq.c.stream_count, 0).label("stream_count"),
        )
        .join(Release, Release.id == Song.release_id)
        .outerjoin(stream_counts_subq, stream_counts_subq.c.song_id == Song.id)
        .filter(
            Song.artist_id == int(artist_id),
            Song.deleted_at.is_(None),
            Song.upload_status == "ready",
            Release.state == RELEASE_STATE_PUBLISHED,
        )
    )

    if sort == "new":
        track_query = track_query.order_by(
            Release.release_date.desc().nullslast(),
            Song.created_at.desc(),
            Song.id.desc(),
        )
    elif sort == "old":
        track_query = track_query.order_by(
            Release.release_date.asc().nullslast(),
            Song.created_at.asc(),
            Song.id.asc(),
        )
    else:
        track_query = track_query.order_by(
            func.coalesce(stream_counts_subq.c.stream_count, 0).desc(),
            Song.created_at.desc(),
            Song.id.desc(),
        )

    track_rows = track_query.limit(10).all()
    song_ids = [int(row[0].id) for row in track_rows]
    track_release_ids = sorted(
        {
            int(row[1].id)
            for row in track_rows
            if getattr(row[1], "id", None) is not None
        }
    )
    media_rows = []
    if song_ids:
        media_rows = (
            db.query(SongMediaAsset)
            .filter(
                SongMediaAsset.song_id.in_(song_ids),
                SongMediaAsset.kind == SONG_MEDIA_KIND_MASTER_AUDIO,
            )
            .all()
        )

    track_release_cover_rows = []
    if track_release_ids:
        track_release_cover_rows = (
            db.query(ReleaseMediaAsset.release_id, ReleaseMediaAsset.file_path)
            .filter(
                ReleaseMediaAsset.release_id.in_(track_release_ids),
                ReleaseMediaAsset.asset_type == RELEASE_MEDIA_ASSET_TYPE_COVER_ART,
            )
            .all()
        )
    track_release_cover_map: dict[int, str] = {}
    for release_id, file_path in track_release_cover_rows:
        rid = int(release_id)
        if rid in track_release_cover_map:
            continue
        if file_path is None:
            continue
        path = str(file_path).strip()
        if not path:
            continue
        track_release_cover_map[rid] = path

    master_map: dict[int, SongMediaAsset] = {}
    for asset in media_rows:
        sid = int(asset.song_id)
        if asset.kind == SONG_MEDIA_KIND_MASTER_AUDIO and sid not in master_map:
            master_map[sid] = asset

    tracks_payload = []
    for song, release, stream_count in track_rows:
        sid = int(song.id)
        master = master_map.get(sid)
        track_cover_url = public_media_url_from_stored_path(
            track_release_cover_map.get(int(release.id))
        )
        tracks_payload.append(
            {
                "id": sid,
                "slug": song.slug,
                "title": song.title,
                "artist_name": artist.name,
                "duration_seconds": song.duration_seconds,
                "release_date": release.release_date.isoformat() if release.release_date else None,
                "stream_count": int(stream_count or 0),
                "cover_url": track_cover_url,
                "audio_url": public_media_url_from_stored_path(master.file_path if master else None),
                "playable": bool(master is not None),
            }
        )

    return {
        "artist_id": int(artist_id),
        "sort": sort,
        "releases": releases_payload,
        "tracks": tracks_payload,
    }


@router.get("/studio/{artist_id}/releases")
def get_studio_releases(
    artist_id: int,
    _owned_artist: Artist = Depends(require_artist_owner),
    db=Depends(get_db),
):
    """All published releases for studio catalog (full grid); same row shape as catalog `releases`."""
    release_rows = (
        db.query(Release)
        .filter(
            Release.artist_id == int(artist_id),
            Release.state == RELEASE_STATE_PUBLISHED,
        )
        .order_by(
            case(
                (
                    Release.state == RELEASE_STATE_PUBLISHED,
                    func.coalesce(Release.discoverable_at, Release.created_at),
                ),
                else_=Release.discoverable_at,
            ).desc()
        )
        .all()
    )

    release_ids = [int(r.id) for r in release_rows]
    release_cover_map: dict[int, str] = {}
    if release_ids:
        for release_id, file_path in (
            db.query(ReleaseMediaAsset.release_id, ReleaseMediaAsset.file_path)
            .filter(
                ReleaseMediaAsset.release_id.in_(release_ids),
                ReleaseMediaAsset.asset_type == RELEASE_MEDIA_ASSET_TYPE_COVER_ART,
            )
            .all()
        ):
            rid = int(release_id)
            if rid in release_cover_map:
                continue
            if file_path is None:
                continue
            path = str(file_path).strip()
            if not path:
                continue
            release_cover_map[rid] = path

    artist = _get_public_artist_or_404(db, int(artist_id))

    first_song_by_release = _get_first_tracks_for_releases(db, release_ids)

    first_song_ids = [int(s.id) for s in first_song_by_release.values()]
    first_master_map: dict[int, SongMediaAsset] = {}
    if first_song_ids:
        for asset in (
            db.query(SongMediaAsset)
            .filter(
                SongMediaAsset.song_id.in_(first_song_ids),
                SongMediaAsset.kind == SONG_MEDIA_KIND_MASTER_AUDIO,
            )
            .all()
        ):
            sid = int(asset.song_id)
            if asset.kind == SONG_MEDIA_KIND_MASTER_AUDIO and sid not in first_master_map:
                first_master_map[sid] = asset

    releases_payload: list[dict] = []
    for release in release_rows:
        rid = int(release.id)
        rel_cover = public_media_url_from_stored_path(release_cover_map.get(rid))
        song = first_song_by_release.get(rid)
        first_track_payload = None
        if song is not None:
            sid = int(song.id)
            master = first_master_map.get(sid)
            track_cover_url = rel_cover
            first_track_payload = {
                "id": sid,
                "slug": song.slug,
                "title": song.title,
                "artist_name": artist.name,
                "duration_seconds": song.duration_seconds,
                "release_date": release.release_date.isoformat()
                if release.release_date
                else None,
                "stream_count": 0,
                "cover_url": track_cover_url,
                "audio_url": public_media_url_from_stored_path(
                    master.file_path if master else None
                ),
                "playable": bool(master is not None),
            }
        releases_payload.append(
            {
                "id": rid,
                "slug": release.slug,
                "title": release.title,
                "type": release.type,
                "release_date": release.release_date.isoformat()
                if release.release_date
                else None,
                "cover_url": rel_cover,
                "first_track": first_track_payload,
            }
        )

    return {"releases": releases_payload}


@router.get(
    "/studio/pending-approvals",
    response_model=PendingApprovalsResponse | PendingApprovalsListResponse,
)
def get_studio_pending_approvals(
    view: Literal["list"] | None = Query(default=None),
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    owned_artist_rows = (
        db.query(Artist.id, Artist.name)
        .filter(Artist.owner_user_id == int(user.id))
        .all()
    )
    owned_artist_ids = {int(row[0]) for row in owned_artist_rows}
    if not owned_artist_ids:
        return []

    release_id_rows = (
        db.query(ReleaseParticipant.release_id)
        .join(Release, Release.id == ReleaseParticipant.release_id)
        .filter(
            ReleaseParticipant.artist_id.in_(owned_artist_ids),
            ReleaseParticipant.status == RELEASE_PARTICIPANT_STATUS_PENDING,
            ReleaseParticipant.requires_approval.is_(True),
        )
        .distinct()
        .all()
    )
    release_ids = [int(row[0]) for row in release_id_rows]
    if not release_ids:
        return []

    grouped = _build_release_decision_payloads(
        db=db,
        release_ids=release_ids,
        owned_artist_ids=owned_artist_ids,
    )
    ordered_release_ids = sorted(
        release_ids,
        key=lambda rid: (
            0
            if any(
                bool(p.get("is_actionable_for_user")) and bool(p.get("blocking"))
                for p in grouped[rid]["participants"]
            )
            else 1,
            -int((grouped[rid]["_updated_at"] or grouped[rid]["_created_at"]).timestamp())
            if (grouped[rid]["_updated_at"] or grouped[rid]["_created_at"]) is not None
            else 0,
            -rid,
        ),
    )
    payload = []
    for rid in ordered_release_ids:
        item = dict(grouped[rid])
        item.pop("_updated_at", None)
        item.pop("_created_at", None)
        if view == "list":
            payload.append(
                {
                    "release": {
                        "id": item["release"]["id"],
                        "title": item["release"]["title"],
                        "cover_url": item["release"]["cover_url"],
                        "artist": item["release"]["artist"],
                        "type": item["release"]["type"],
                        "created_at": item["release"]["created_at"],
                        "track_count": item["release"]["track_count"],
                        "split_version": item["release"]["split_version"],
                    },
                    "approval_status": item["approval_status"],
                    "pending_summary": item["pending_summary"],
                    "participants": [
                        {
                            "artist_id": p["artist_id"],
                            "artist_name": p["artist_name"],
                            "role": p["role"],
                            "status": p["status"],
                            "approval_type": p["approval_type"],
                            "blocking": p["blocking"],
                            "is_actionable_for_user": bool(
                                p.get("is_actionable_for_user", False)
                            ),
                        }
                        for p in item["participants"]
                    ],
                }
            )
            continue
        payload.append(item)
    return payload


@router.get("/studio/releases/{release_id}", response_model=ReleaseDetailResponse)
def get_studio_release_detail(
    release_id: int,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    owned_artist_rows = (
        db.query(Artist.id, Artist.name)
        .filter(Artist.owner_user_id == int(user.id))
        .all()
    )
    owned_artist_ids = {int(row[0]) for row in owned_artist_rows}

    release = db.query(Release).filter(Release.id == int(release_id)).first()
    if release is None:
        raise HTTPException(status_code=404, detail="Release not found")

    access_row = (
        db.query(ReleaseParticipant.id)
        .join(Artist, Artist.id == ReleaseParticipant.artist_id)
        .filter(
            ReleaseParticipant.release_id == int(release_id),
            Artist.owner_user_id == int(user.id),
        )
        .first()
    )
    if access_row is None:
        raise HTTPException(status_code=404, detail="Release not found")

    grouped = _build_release_decision_payloads(
        db=db,
        release_ids=[int(release_id)],
        owned_artist_ids=owned_artist_ids,
    )
    if int(release_id) not in grouped:
        raise HTTPException(status_code=404, detail="Release not found")
    item = grouped[int(release_id)]
    payload = {
        "release": {
            **item["release"],
            "approval_status": item["approval_status"],
        },
        "user_context": {
            "owned_artist_ids": sorted(owned_artist_ids),
            "pending_actions_count": sum(
                1 for p in item["participants"] if bool(p.get("is_actionable_for_user"))
            ),
        },
        "songs": item["songs"],
        "splits": item["splits"],
        "participants": item["participants"],
        "pending_summary": item["pending_summary"],
    }
    return payload


@router.get("/studio/{artist_id}/dashboard")
def get_studio_artist_dashboard(
    artist_id: int,
    _owned_artist: Artist = Depends(require_artist_owner),
):
    return get_artist_dashboard(int(artist_id))


@router.get("/studio/{artist_id}/analytics")
def get_studio_artist_analytics(
    artist_id: int,
    range: str = Query("last_30_days", description="Time range preset"),
    _owned_artist: Artist = Depends(require_artist_owner),
):
    aid = int(artist_id)
    try:
        streams = get_artist_streams_over_time(artist_id=aid, range=range)
        top_songs = get_artist_top_songs(artist_id=aid, range=range)
        top_fans = get_artist_top_fans(artist_id=aid, range=range)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid range")
    return {
        "range": range,
        "streams": streams,
        "top_songs": top_songs,
        "top_fans": top_fans,
    }


@router.get("/studio/{artist_id}/payouts")
def get_studio_artist_payouts(
    artist_id: int,
    _owned_artist: Artist = Depends(require_artist_owner),
):
    summary = get_artist_payout_summary(int(artist_id))
    history = get_artist_payout_history(int(artist_id))
    capabilities = get_artist_payout_capabilities(int(artist_id))

    def cents_to_eur(cents: int) -> float:
        return float((Decimal(int(cents)) / Decimal("100")).quantize(Decimal("0.01")))

    last_batch_date = summary.get("last_batch_date")
    summary_payload = {
        "paid_eur": cents_to_eur(int(summary.get("paid_cents", 0))),
        "accrued_eur": cents_to_eur(int(summary.get("accrued_cents", 0))),
        "pending_eur": cents_to_eur(int(summary.get("pending_cents", 0))),
        "failed_eur": cents_to_eur(int(summary.get("failed_cents", 0))),
        "batch_count": int(summary.get("batch_count", 0)),
        "last_batch_date": last_batch_date.isoformat() if last_batch_date is not None else None,
    }

    history_payload = []
    for row in history:
        row_date = row.get("date")
        history_payload.append(
            {
                "batch_id": str(row.get("batch_id")),
                "date": row_date.isoformat() if row_date is not None else "",
                "amount_eur": cents_to_eur(int(row.get("amount_cents", 0))),
                "status": str(row.get("status") or "pending"),
                "users": int(row.get("distinct_users", 0)),
                "tx_id": row.get("tx_id"),
                "explorer_url": row.get("explorer_url"),
            }
        )

    selected = str(capabilities.get("payout_method_selected") or "none").strip().lower()
    if selected not in ("crypto", "bank", "none"):
        selected = "none"
    payout_method_payload = {
        "selected": selected,
        "supports_onchain_settlement": bool(
            capabilities.get("supports_onchain_settlement", False)
        ),
        "requires_manual_settlement": bool(
            capabilities.get("requires_manual_settlement", False)
        ),
        "wallet_address": capabilities.get("wallet_address"),
        "bank_configured": bool(capabilities.get("bank_configured", False)),
    }

    return {
        "summary": summary_payload,
        "history": history_payload,
        "payout_method": payout_method_payload,
    }


@router.post("/studio/context")
def post_studio_context(
    body: StudioContextBody,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    context = validate_context_for_user_or_403(
        db=db,
        user=user,
        context_type=body.type,
        context_id=int(body.id),
    )
    # Defensive re-check to keep endpoint fail-closed if helper behavior changes.
    if not is_context_allowed_for_user(
        db=db,
        user=user,
        context_type=context["type"],
        context_id=int(context["id"]),
    ):
        raise HTTPException(status_code=403, detail="Context not allowed for this user")

    user.current_context_type = str(context["type"])
    user.current_context_id = int(context["id"])
    db.add(user)
    db.commit()
    db.refresh(user)

    return {"current_context": get_current_context(db=db, user=user)}


class StartSessionRequest(BaseModel):
    song_id: int
    discovery_request_id: str | None = None
    discovery_section: str | None = None
    discovery_position: int | None = None
    source_type: str | None = Field(
        default=None,
        description=(
            "Optional playback attribution: playlist | discovery | search | direct. "
            "Omit for legacy clients."
        ),
    )
    source_id: str | None = Field(
        default=None,
        description="Opaque id for the source (e.g. playlist id). Requires source_type when set.",
    )


class StreamEventRequest(BaseModel):
    song_id: int = Field(..., examples=[1], description="Song being streamed")
    duration: int = Field(..., examples=[30], description="Played seconds in this event")
    session_id: int | None = Field(
        default=None,
        examples=[101],
        description="Optional listening session id from /stream/start-session",
    )
    idempotency_key: str | None = Field(
        default=None,
        examples=["strm-1-song-1-30s"],
        description="Optional dedupe key for safe retries",
    )
    correlation_id: str | None = Field(
        default=None,
        examples=["mobile-playback-2026-04-21-001"],
        description="Optional trace id across logs",
    )


class DevStreamRequest(BaseModel):
    user_id: int = Field(..., examples=[1], description="Listener user id (dev only)")
    song_id: int = Field(..., examples=[1], description="Song id")
    duration: int = Field(..., examples=[30], description="Played seconds")
    session_id: int | None = Field(
        default=None,
        examples=[101],
        description="Existing session id when testing checkpoint flow",
    )
    idempotency_key: str | None = Field(
        default=None,
        examples=["dev-user1-song1-30s"],
        description="Optional dedupe key for retries",
    )
    correlation_id: str | None = Field(
        default=None,
        examples=["qa-run-42"],
        description="Optional trace id",
    )


@router.post("/songs")
def post_create_song(
    body: CreateSongBody,
    db=Depends(get_db),
    _owned_artist: Artist = Depends(_require_owner_for_create_song),
):
    """
    Create a song with title, primary artist, optional featuring artists and credits.
    Does not upload audio or set splits; those use other endpoints.
    """
    title_stripped = (body.title or "").strip()
    if not title_stripped:
        raise HTTPException(status_code=400, detail="Title is required")
    try:
        song = create_song_with_metadata(
            db,
            title=title_stripped,
            artist_id=body.artist_id,
            release_id=body.release_id,
            featured_artist_ids=body.featured_artist_ids,
            credits=[c.model_dump() for c in body.credits],
            genre_id=body.genre_id,
            subgenre_id=body.subgenre_id,
            moods=body.moods,
            country_code=body.country_code,
            city=body.city,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    moods_resp = None
    if song.moods is not None:
        moods_resp = [str(m) for m in song.moods]

    return {
        "song_id": song.id,
        "title": song.title,
        "artist_id": song.artist_id,
        "featured_artist_ids": list(body.featured_artist_ids),
        "credits": [c.model_dump() for c in body.credits],
        "genre_id": song.genre_id,
        "subgenre_id": song.subgenre_id,
        "moods": moods_resp,
        "country_code": song.country_code,
        "city": song.city,
    }


@router.get("/genres")
def list_genres(db=Depends(get_db)):
    """Canonical main genres (fixed product order) with stable slugs."""
    whens = [
        (Genre.slug == slug, idx) for idx, (_n, slug) in enumerate(CANONICAL_GENRE_ORDER)
    ]
    ordering = case(*whens, else_=999)
    rows = db.query(Genre).order_by(ordering, Genre.name.asc()).all()
    return [{"id": int(r.id), "name": r.name, "slug": r.slug} for r in rows]


@router.get("/genres/{genre_id}/subgenres")
def list_subgenres_for_genre(genre_id: int, db=Depends(get_db)):
    if db.query(Genre.id).filter(Genre.id == int(genre_id)).first() is None:
        raise HTTPException(status_code=404, detail="Genre not found")
    # TODO: consider sort_order column if UX requires non-alphabetical ordering
    rows = (
        db.query(Subgenre)
        .filter(Subgenre.genre_id == int(genre_id))
        .order_by(Subgenre.name.asc())
        .all()
    )
    return [{"id": int(r.id), "name": r.name, "slug": r.slug} for r in rows]


@router.post("/releases")
def post_create_release(
    body: CreateReleaseBody,
    db=Depends(get_db),
    user: User = Depends(get_current_user),
    _owned_artist: Artist = Depends(_require_owner_for_create_release),
):
    """Create a draft release (single or album)."""
    try:
        rdt = datetime.fromisoformat(body.release_date.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail="release_date must be a valid ISO 8601 datetime string",
        ) from exc
    try:
        release = create_release(
            db,
            title=body.title,
            artist_id=body.artist_id,
            release_type=body.release_type,
            release_date=rdt,
            owner_user_id=int(user.id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "release_id": int(release.id),
        "title": release.title,
        "type": release.type,
    }


@router.post("/studio/releases/{release_id}/publish")
def post_studio_release_publish(
    release_id: int,
    db=Depends(get_db),
    user: User = Depends(get_current_user),
):
    release = db.query(Release).filter(Release.id == int(release_id)).first()
    if release is None:
        raise HTTPException(status_code=404, detail="Release not found")

    try:
        enforce_artist_ownership(
            artist_id=int(release.artist_id),
            user=user,
            db=db,
        )
    except HTTPException as exc:
        if int(exc.status_code) == 404:
            raise HTTPException(status_code=404, detail="Release not found") from exc
        raise

    try:
        published = publish_release(db, release_id=int(release_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "release_id": int(published.id),
        "state": str(published.state),
        "discoverable_at": (
            published.discoverable_at.isoformat() if published.discoverable_at else None
        ),
    }


@router.get("/studio/releases/{release_id}/approvals")
def get_release_approvals(
    release_id: int,
    db=Depends(get_db),
    _owned_release: Release = Depends(require_release_owner),
):
    rows = list_release_approvals(db, release_id=int(release_id))
    return {
        "release_id": int(release_id),
        "participants": [
            {
                "artist_id": int(row.artist_id),
                "role": row.role,
                "status": row.status,
                "approval_type": row.approval_type,
                "requires_approval": bool(row.requires_approval),
                "approved_at": row.approved_at.isoformat() if row.approved_at else None,
                "rejection_reason": row.rejection_reason,
            }
            for row in rows
        ],
    }


@router.post("/studio/releases/{release_id}/approve", response_model=ApprovalActionResponse)
def post_release_approve(
    release_id: int,
    body: ReleaseApprovalActionBody,
    db=Depends(get_db),
    user: User = Depends(get_current_user),
    _participant_actor: ReleaseParticipant = Depends(_require_participant_actor_for_release_approval_action),
):
    try:
        participant = approve_participation(
            db,
            release_id=int(release_id),
            artist_id=int(body.artist_id),
            user=user,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    release = db.query(Release).filter(Release.id == int(release_id)).first()
    release_approval_status = str(release.approval_status) if release is not None else None
    approval_type = str(participant.approval_type)
    return {
        "status": "accepted",
        "updated_participant": {
            "artist_id": int(participant.artist_id),
            "role": participant.role,
            "approval_type": approval_type,
            "blocking": approval_type == "split",
            "status": participant.status,
            "rejection_reason": participant.rejection_reason,
            "approved_at": participant.approved_at.isoformat() if participant.approved_at else None,
        },
        "release_approval_status": release_approval_status,
    }


@router.post("/studio/releases/{release_id}/reject", response_model=ApprovalActionResponse)
def post_release_reject(
    release_id: int,
    body: ReleaseApprovalActionBody,
    db=Depends(get_db),
    user: User = Depends(get_current_user),
    _participant_actor: ReleaseParticipant = Depends(_require_participant_actor_for_release_approval_action),
):
    pre_role = str(_participant_actor.role)
    pre_approval_type = str(_participant_actor.approval_type)
    try:
        reject_participation(
            db,
            release_id=int(release_id),
            artist_id=int(body.artist_id),
            user=user,
            reason=body.reason,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    release = db.query(Release).filter(Release.id == int(release_id)).first()
    release_approval_status = str(release.approval_status) if release is not None else None
    participant = (
        db.query(ReleaseParticipant)
        .filter(
            ReleaseParticipant.release_id == int(release_id),
            ReleaseParticipant.artist_id == int(body.artist_id),
        )
        .first()
    )
    if participant is not None:
        approval_type = str(participant.approval_type)
        updated_participant = {
            "artist_id": int(participant.artist_id),
            "role": participant.role,
            "approval_type": approval_type,
            "blocking": approval_type == "split",
            "status": participant.status,
            "rejection_reason": participant.rejection_reason,
            "approved_at": participant.approved_at.isoformat() if participant.approved_at else None,
        }
    else:
        updated_participant = {
            "artist_id": int(body.artist_id),
            "role": pre_role,
            "approval_type": pre_approval_type,
            "blocking": pre_approval_type == "split",
            "status": "rejected",
            "rejection_reason": (str(body.reason).strip() if body.reason else None) or None,
            "approved_at": None,
        }
    return {
        "status": "rejected",
        "updated_participant": updated_participant,
        "release_approval_status": release_approval_status,
    }


@router.get("/songs/{song_id}")
def get_song(song_id: int, db=Depends(get_db)):
    """
    Song detail for upload wizard: status, duration, media flags, metadata joins.
    ``cover_url`` is a path relative to the API host (static ``/uploads`` mount).
    """
    song = (
        db.query(Song)
        .options(joinedload(Song.genre), joinedload(Song.subgenre))
        .filter(Song.id == int(song_id), Song.deleted_at.is_(None))
        .first()
    )
    if song is None:
        raise HTTPException(status_code=404, detail="Song not found")

    featured_rows = (
        db.query(SongFeaturedArtist.artist_id)
        .filter(SongFeaturedArtist.song_id == int(song_id))
        .order_by(SongFeaturedArtist.position.asc())
        .all()
    )
    featured_artist_ids = [int(r[0]) for r in featured_rows]

    credit_rows = (
        db.query(SongCreditEntry.display_name, SongCreditEntry.role)
        .filter(SongCreditEntry.song_id == int(song_id))
        .order_by(SongCreditEntry.position.asc())
        .all()
    )
    credits = [{"name": str(n), "role": str(role)} for n, role in credit_rows]

    master = (
        db.query(SongMediaAsset)
        .filter(
            SongMediaAsset.song_id == int(song_id),
            SongMediaAsset.kind == SONG_MEDIA_KIND_MASTER_AUDIO,
        )
        .first()
    )
    has_master_audio = master is not None
    cover_path_raw = effective_song_cover(db, song)
    cover_url = public_media_url_from_stored_path(cover_path_raw)
    has_cover_art = cover_path_raw is not None

    def _taxon(entity: Genre | Subgenre | None):
        if entity is None:
            return None
        return {"id": int(entity.id), "name": entity.name, "slug": entity.slug}

    moods_out = None
    if song.moods is not None:
        moods_out = [str(m) for m in song.moods]

    split_rows = (
        db.query(SongArtistSplit.artist_id, SongArtistSplit.share)
        .filter(SongArtistSplit.song_id == int(song_id))
        .order_by(SongArtistSplit.artist_id.asc())
        .all()
    )
    splits_out = [
        {"artist_id": int(aid), "share": float(share)} for aid, share in split_rows
    ]

    return {
        "id": song.id,
        "slug": song.slug,
        "title": song.title,
        "artist_id": song.artist_id,
        "release_id": int(song.release_id) if song.release_id is not None else None,
        "upload_status": song.upload_status,
        "duration_seconds": song.duration_seconds,
        "featured_artist_ids": featured_artist_ids,
        "credits": credits,
        "splits": splits_out,
        "has_master_audio": has_master_audio,
        "has_cover_art": has_cover_art,
        "cover_url": cover_url,
        "genre_id": song.genre_id,
        "subgenre_id": song.subgenre_id,
        "genre": _taxon(song.genre),
        "subgenre": _taxon(song.subgenre),
        "moods": moods_out,
        "country_code": song.country_code,
        "city": song.city,
    }


@router.patch("/songs/{song_id}")
def patch_song_metadata(
    song_id: int,
    body: PatchSongBody,
    db=Depends(get_db),
    song: Song = Depends(require_song_owner),
):
    """Update song metadata for the upload wizard; respects ready-state locks."""
    if int(body.artist_id) != int(song.artist_id):
        raise HTTPException(
            status_code=400,
            detail="artist_id does not match this song's primary artist.",
        )
    try:
        update_existing_song_metadata(
            db,
            song_id,
            title=body.title,
            featured_artist_ids=list(body.featured_artist_ids),
            credits=[c.model_dump() for c in body.credits],
            genre_id=body.genre_id,
            subgenre_id=body.subgenre_id,
            moods=body.moods,
            country_code=body.country_code,
            city=body.city,
        )
    except ValueError as exc:
        msg = str(exc)
        if msg in {"title_locked", "featured_locked"}:
            raise HTTPException(status_code=400, detail=msg) from exc
        raise HTTPException(status_code=400, detail=msg) from exc
    return {"status": "ok", "song_id": int(song_id)}


@router.delete("/songs/{song_id}")
def delete_song_endpoint(
    song_id: int,
    db=Depends(get_db),
    song: Song = Depends(require_song_owner),
):
    """Soft-delete a song (sets deleted_at; owner-only)."""
    song.deleted_at = datetime.utcnow()
    db.add(song)
    db.commit()
    return {"status": "ok", "song_id": int(song_id)}


@router.get("/releases/{release_id}/tracks")
def get_release_tracks_view(release_id: int, db=Depends(get_db)):
    try:
        tracks = get_release_tracks(db, int(release_id))
        progress = get_release_progress(db, int(release_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "tracks": tracks,
        "progress": progress,
    }


@router.post("/releases/{release_id}/upload-cover")
def post_release_upload_cover(
    release_id: int,
    file: UploadFile = File(...),
    db=Depends(get_db),
    _owned_release: Release = Depends(require_release_owner),
):
    """Upload cover art (JPEG/PNG) for a release; stored as ``ReleaseMediaAsset``."""
    try:
        upload_release_cover_art(
            db,
            int(release_id),
            file.file,
            original_filename=file.filename,
            content_type=file.content_type,
        )
        db.commit()
    except CoverResolutionInvalidError:
        db.rollback()
        return JSONResponse(
            status_code=400,
            content={"error": "cover_resolution_invalid"},
        )
    except ValueError as exc:
        db.rollback()
        raise _http_from_upload_value_error(exc) from exc

    return {"status": "ok", "release_id": int(release_id)}


_MAX_ARTIST_SEARCH_Q_LEN = 128
_MAX_GLOBAL_SEARCH_Q_LEN = 128


def _escape_like_pattern(s: str) -> str:
    """Escape ``%``, ``_``, and ``\\`` for SQL LIKE with ESCAPE '\\'."""
    return (
        s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    )


@router.get("/artists/search")
def search_artists(
    q: str = Query(...),
    limit: int = Query(10, ge=1, le=25),
    db=Depends(get_db),
):
    """Case-insensitive name substring search; excludes system artists."""
    trimmed = (q or "").strip()
    if not trimmed:
        return {"artists": []}
    if len(trimmed) > _MAX_ARTIST_SEARCH_Q_LEN:
        trimmed = trimmed[:_MAX_ARTIST_SEARCH_Q_LEN]
    pattern = f"%{_escape_like_pattern(trimmed.lower())}%"
    rows = (
        db.query(Artist)
        .filter(
            Artist.is_system.is_(False),
            func.lower(Artist.name).like(pattern, escape="\\"),
        )
        .order_by(Artist.name.asc())
        .limit(limit)
        .all()
    )
    return {
        "artists": [{"id": int(a.id), "name": a.name, "slug": a.slug} for a in rows],
    }


@router.get("/search")
def global_search(
    q: str = Query(...),
    limit: int = Query(10, ge=1, le=25),
    db=Depends(get_db),
):
    trimmed = (q or "").strip()
    if len(trimmed) < 2:
        return {
            "results": [],
            "groups": {"artists": [], "tracks": [], "albums": []},
            "meta": {"query": trimmed, "limit": int(limit)},
        }
    if len(trimmed) > _MAX_GLOBAL_SEARCH_Q_LEN:
        trimmed = trimmed[:_MAX_GLOBAL_SEARCH_Q_LEN]
    return search_global(db, query=trimmed, limit=int(limit))


@router.get("/artists/{artist_id}")
def get_artist(artist_id: int, db=Depends(get_db)):
    """Public artist record for clients (e.g. upload wizard)."""
    artist = _get_public_artist_or_404(db, artist_id)
    return {"id": artist.id, "name": artist.name, "slug": artist.slug}


@router.get("/artists/{artist_id}/songs")
def list_artist_songs(
    artist_id: int,
    limit: int = Query(50, ge=1, le=200),
    db=Depends(get_db),
):
    """Catalog list for an artist: metadata and public media paths for future playback."""
    _get_public_artist_or_404(db, artist_id)
    songs = (
        db.query(Song)
        .filter(Song.artist_id == int(artist_id), Song.deleted_at.is_(None))
        .order_by(desc(Song.created_at))
        .limit(int(limit))
        .all()
    )
    if not songs:
        return {"songs": []}

    song_ids = [int(s.id) for s in songs]
    assets = (
        db.query(SongMediaAsset)
        .filter(
            SongMediaAsset.song_id.in_(song_ids),
            SongMediaAsset.kind == SONG_MEDIA_KIND_MASTER_AUDIO,
        )
        .all()
    )
    master_by_sid: dict[int, SongMediaAsset] = {}
    for asset in assets:
        sid = int(asset.song_id)
        if asset.kind == SONG_MEDIA_KIND_MASTER_AUDIO:
            master_by_sid[sid] = asset

    release_ids = {int(s.release_id) for s in songs if s.release_id is not None}
    releases_by_id: dict[int, Release] = {}
    if release_ids:
        for r in db.query(Release).filter(Release.id.in_(release_ids)).all():
            releases_by_id[int(r.id)] = r

    album_cover_path_by_rid: dict[int, str] = {}
    if release_ids:
        for a in (
            db.query(ReleaseMediaAsset)
            .filter(
                ReleaseMediaAsset.release_id.in_(release_ids),
                ReleaseMediaAsset.asset_type == RELEASE_MEDIA_ASSET_TYPE_COVER_ART,
            )
            .all()
        ):
            if a.file_path and str(a.file_path).strip():
                album_cover_path_by_rid[int(a.release_id)] = str(a.file_path).strip()

    payload = []
    for song in songs:
        sid = int(song.id)
        master = master_by_sid.get(sid)
        has_master_audio = master is not None
        rel = releases_by_id.get(int(song.release_id)) if song.release_id is not None else None
        acp = album_cover_path_by_rid.get(int(rel.id)) if rel is not None else None
        cover_path = acp if rel is not None else effective_song_cover(db, song)
        cover_url = public_media_url_from_stored_path(cover_path)
        audio_url = public_media_url_from_stored_path(
            master.file_path if master else None,
        )
        upload_status = str(song.upload_status or "")
        playable = has_master_audio and upload_status == "ready"
        payload.append(
            {
                "id": sid,
                "slug": song.slug,
                "title": song.title,
                "artist_id": int(song.artist_id),
                "release_id": int(song.release_id) if song.release_id is not None else None,
                "release_slug": rel.slug if rel is not None else None,
                "upload_status": upload_status,
                "duration_seconds": song.duration_seconds,
                "cover_url": cover_url,
                "audio_url": audio_url,
                "has_master_audio": has_master_audio,
                "playable": playable,
            }
        )
    return {"songs": payload}


@router.get("/artist/{slug}")
def get_artist_by_slug(slug: str, db=Depends(get_db)):
    artist, is_current = resolve_artist_slug(db, slug)
    if artist is None or bool(artist.is_system):
        raise HTTPException(status_code=404, detail="Artist not found")
    canonical_slug = str(artist.slug or "").strip()
    if not canonical_slug:
        raise HTTPException(status_code=404, detail="Artist not found")
    if not is_current or canonical_slug != slug:
        return RedirectResponse(url=f"/artist/{quote(canonical_slug)}", status_code=301)
    songs_payload = list_artist_songs(artist_id=int(artist.id), limit=50, db=db)
    return {
        "id": int(artist.id),
        "slug": canonical_slug,
        "name": artist.name,
        "canonical_url": _artist_slug_href(canonical_slug),
        "songs": songs_payload.get("songs", []),
    }


@router.get("/artist/{slug}/releases")
def get_artist_releases_by_slug(slug: str, db=Depends(get_db)):
    artist, is_current = resolve_artist_slug(db, slug)
    if artist is None or bool(artist.is_system):
        raise HTTPException(status_code=404, detail="Artist not found")
    canonical_slug = str(artist.slug or "").strip()
    if not canonical_slug:
        raise HTTPException(status_code=404, detail="Artist not found")
    if not is_current or canonical_slug != slug:
        return RedirectResponse(
            url=f"/artist/{quote(canonical_slug)}/releases",
            status_code=301,
        )

    release_rows = (
        db.query(Release)
        .filter(
            Release.artist_id == int(artist.id),
            Release.state == RELEASE_STATE_PUBLISHED,
        )
        .order_by(
            case(
                (
                    Release.state == RELEASE_STATE_PUBLISHED,
                    func.coalesce(Release.discoverable_at, Release.created_at),
                ),
                else_=Release.discoverable_at,
            ).desc()
        )
        .all()
    )
    release_ids = [int(r.id) for r in release_rows]

    release_cover_map: dict[int, str] = {}
    if release_ids:
        for release_id, file_path in (
            db.query(ReleaseMediaAsset.release_id, ReleaseMediaAsset.file_path)
            .filter(
                ReleaseMediaAsset.release_id.in_(release_ids),
                ReleaseMediaAsset.asset_type == RELEASE_MEDIA_ASSET_TYPE_COVER_ART,
            )
            .all()
        ):
            rid = int(release_id)
            if rid in release_cover_map:
                continue
            if file_path is None:
                continue
            path = str(file_path).strip()
            if not path:
                continue
            release_cover_map[rid] = path

    first_song_by_release = _get_first_tracks_for_releases(db, release_ids)
    first_song_ids = [int(s.id) for s in first_song_by_release.values()]

    first_master_map: dict[int, SongMediaAsset] = {}
    if first_song_ids:
        for asset in (
            db.query(SongMediaAsset)
            .filter(
                SongMediaAsset.song_id.in_(first_song_ids),
                SongMediaAsset.kind == SONG_MEDIA_KIND_MASTER_AUDIO,
            )
            .all()
        ):
            sid = int(asset.song_id)
            if asset.kind == SONG_MEDIA_KIND_MASTER_AUDIO and sid not in first_master_map:
                first_master_map[sid] = asset

    releases_payload: list[dict] = []
    for release in release_rows:
        rid = int(release.id)
        rel_cover = public_media_url_from_stored_path(release_cover_map.get(rid))
        song = first_song_by_release.get(rid)
        first_track_payload = None
        if song is not None:
            sid = int(song.id)
            master = first_master_map.get(sid)
            first_track_payload = {
                "id": sid,
                "slug": song.slug,
                "title": song.title,
                "artist_name": artist.name,
                "duration_seconds": song.duration_seconds,
                "release_date": release.release_date.isoformat()
                if release.release_date
                else None,
                "stream_count": 0,
                "cover_url": rel_cover,
                "audio_url": public_media_url_from_stored_path(
                    master.file_path if master else None
                ),
                "playable": bool(master is not None),
            }
        releases_payload.append(
            {
                "id": rid,
                "slug": release.slug,
                "title": release.title,
                "type": release.type,
                "release_date": release.release_date.isoformat()
                if release.release_date
                else None,
                "cover_url": rel_cover,
                "first_track": first_track_payload,
            }
        )

    return {
        "artist": {
            "id": int(artist.id),
            "slug": canonical_slug,
            "name": artist.name,
        },
        "releases": releases_payload,
    }


@router.get("/artist/{slug}/tracks")
def get_artist_tracks_by_slug(
    slug: str,
    sort: Literal["top", "new", "old"] = Query(default="top"),
    limit: int = Query(default=10, ge=1, le=50),
    db=Depends(get_db),
):
    artist, is_current = resolve_artist_slug(db, slug)
    if artist is None or bool(artist.is_system):
        raise HTTPException(status_code=404, detail="Artist not found")
    canonical_slug = str(artist.slug or "").strip()
    if not canonical_slug:
        raise HTTPException(status_code=404, detail="Artist not found")
    if not is_current or canonical_slug != slug:
        return RedirectResponse(
            url=f"/artist/{quote(canonical_slug)}/tracks?{urlencode({'sort': sort, 'limit': int(limit)})}",
            status_code=301,
        )

    stream_counts_subq = (
        db.query(
            ListeningEvent.song_id.label("song_id"),
            func.count(ListeningEvent.id).label("stream_count"),
        )
        .filter(
            ListeningEvent.is_valid.is_(True),
            ListeningEvent.validated_duration > 0,
        )
        .group_by(ListeningEvent.song_id)
        .subquery()
    )

    track_query = (
        db.query(
            Song,
            Release,
            func.coalesce(stream_counts_subq.c.stream_count, 0).label("stream_count"),
        )
        .join(Release, Release.id == Song.release_id)
        .outerjoin(stream_counts_subq, stream_counts_subq.c.song_id == Song.id)
        .filter(
            Song.artist_id == int(artist.id),
            Song.deleted_at.is_(None),
            Song.upload_status == "ready",
            Release.state == RELEASE_STATE_PUBLISHED,
        )
    )

    if sort == "new":
        track_query = track_query.order_by(
            Release.release_date.desc().nullslast(),
            Song.created_at.desc(),
            Song.id.desc(),
        )
    elif sort == "old":
        track_query = track_query.order_by(
            Release.release_date.asc().nullslast(),
            Song.created_at.asc(),
            Song.id.asc(),
        )
    else:
        track_query = track_query.order_by(
            func.coalesce(stream_counts_subq.c.stream_count, 0).desc(),
            Song.created_at.desc(),
            Song.id.desc(),
        )

    track_rows = track_query.limit(int(limit)).all()
    song_ids = [int(row[0].id) for row in track_rows]
    track_release_ids = sorted(
        {
            int(row[1].id)
            for row in track_rows
            if getattr(row[1], "id", None) is not None
        }
    )

    media_rows = []
    if song_ids:
        media_rows = (
            db.query(SongMediaAsset)
            .filter(
                SongMediaAsset.song_id.in_(song_ids),
                SongMediaAsset.kind == SONG_MEDIA_KIND_MASTER_AUDIO,
            )
            .all()
        )

    track_release_cover_rows = []
    if track_release_ids:
        track_release_cover_rows = (
            db.query(ReleaseMediaAsset.release_id, ReleaseMediaAsset.file_path)
            .filter(
                ReleaseMediaAsset.release_id.in_(track_release_ids),
                ReleaseMediaAsset.asset_type == RELEASE_MEDIA_ASSET_TYPE_COVER_ART,
            )
            .all()
        )

    track_release_cover_map: dict[int, str] = {}
    for release_id, file_path in track_release_cover_rows:
        rid = int(release_id)
        if rid in track_release_cover_map:
            continue
        if file_path is None:
            continue
        path = str(file_path).strip()
        if not path:
            continue
        track_release_cover_map[rid] = path

    master_map: dict[int, SongMediaAsset] = {}
    for asset in media_rows:
        sid = int(asset.song_id)
        if asset.kind == SONG_MEDIA_KIND_MASTER_AUDIO and sid not in master_map:
            master_map[sid] = asset

    tracks_payload = []
    for song, release, stream_count in track_rows:
        sid = int(song.id)
        master = master_map.get(sid)
        track_cover_url = public_media_url_from_stored_path(
            track_release_cover_map.get(int(release.id))
        )
        tracks_payload.append(
            {
                "id": sid,
                "slug": song.slug,
                "title": song.title,
                "artist_name": artist.name,
                "duration_seconds": song.duration_seconds,
                "release_date": release.release_date.isoformat() if release.release_date else None,
                "stream_count": int(stream_count or 0),
                "cover_url": track_cover_url,
                "audio_url": public_media_url_from_stored_path(master.file_path if master else None),
                "playable": bool(master is not None),
            }
        )

    return {
        "artist": {
            "id": int(artist.id),
            "slug": canonical_slug,
            "name": artist.name,
        },
        "sort": sort,
        "tracks": tracks_payload,
    }


@router.get("/album/{slug}")
def get_album_by_slug(slug: str, db=Depends(get_db)):
    release, is_current = resolve_release_slug(db, slug)
    if release is None:
        raise HTTPException(status_code=404, detail="Album not found")
    canonical_slug = str(release.slug or "").strip()
    if not canonical_slug:
        raise HTTPException(status_code=404, detail="Album not found")
    if not is_current or canonical_slug != slug:
        return RedirectResponse(url=f"/album/{quote(canonical_slug)}", status_code=301)
    artist = _get_public_artist_or_404(db, int(release.artist_id))
    tracks = get_release_tracks_view(release_id=int(release.id), db=db)
    return {
        "id": int(release.id),
        "slug": canonical_slug,
        "title": release.title,
        "type": release.type,
        "artist": {
            "id": int(artist.id),
            "name": artist.name,
            "slug": artist.slug,
        },
        "release_date": release.release_date.isoformat() if release.release_date else None,
        "state": release.state,
        "canonical_url": _album_slug_href(canonical_slug),
        "tracks": tracks.get("tracks", []),
        "progress": tracks.get("progress", {}),
    }


@router.get("/track/{slug}")
def get_track_by_slug(slug: str, db=Depends(get_db)):
    song, is_current = resolve_song_slug(db, slug)
    if song is None:
        raise HTTPException(status_code=404, detail="Track not found")
    canonical_slug = str(song.slug or "").strip()
    if not canonical_slug:
        raise HTTPException(status_code=404, detail="Track not found")
    if not is_current or canonical_slug != slug:
        return RedirectResponse(url=f"/track/{quote(canonical_slug)}", status_code=301)
    detail = get_song(song_id=int(song.id), db=db)
    artist = _get_public_artist_or_404(db, int(song.artist_id))
    album = None
    if song.release_id is not None:
        release = db.query(Release).filter(Release.id == int(song.release_id)).first()
        if release is not None:
            album = {
                "id": int(release.id),
                "slug": release.slug,
                "title": release.title,
            }
    return {
        **detail,
        "id": int(song.id),
        "slug": canonical_slug,
        "artist": {
            "id": int(artist.id),
            "slug": artist.slug,
            "name": artist.name,
        },
        "album": album,
        "canonical_url": _track_slug_href(canonical_slug),
    }


@router.get("/alias/{artist_slug}/{release_slug}/{track_slug}")
def alias_track_path_redirect(
    artist_slug: str,
    release_slug: str,
    track_slug: str,
    db=Depends(get_db),
):
    song, _ = resolve_song_slug(db, track_slug)
    if song is None:
        raise HTTPException(status_code=404, detail="Track not found")
    release = None
    if song.release_id is not None:
        release = db.query(Release).filter(Release.id == int(song.release_id)).first()
    artist = _get_public_artist_or_404(db, int(song.artist_id))
    if artist.slug != artist_slug:
        raise HTTPException(status_code=404, detail="Track not found")
    if release is not None and (release.slug or "") != release_slug:
        raise HTTPException(status_code=404, detail="Track not found")
    canonical = str(song.slug or "").strip()
    if not canonical:
        raise HTTPException(status_code=404, detail="Track not found")
    return RedirectResponse(url=f"/track/{quote(canonical)}", status_code=301)




def _http_from_upload_value_error(exc: ValueError) -> HTTPException:
    msg = str(exc)
    if "not found" in msg.lower():
        return HTTPException(status_code=404, detail=msg)
    return HTTPException(status_code=400, detail=msg)


@router.post("/songs/{song_id}/upload-audio")
def post_song_upload_audio(
    song_id: int,
    file: UploadFile = File(...),
    db=Depends(get_db),
    _owned_song: Song = Depends(require_song_owner),
):
    """Upload master WAV for an existing song; updates ``file_path``, ``duration_seconds``, and ``upload_status``."""
    try:
        duration_seconds = upload_song_master_audio(
            db,
            song_id,
            file.file,
            original_filename=file.filename,
            content_type=file.content_type,
        )
    except WavFileTooLargeError:
        return JSONResponse(
            status_code=400,
            content={"error": "wav_file_too_large"},
        )
    except MasterAudioImmutableError:
        return JSONResponse(
            status_code=400,
            content={"error": "master_audio_immutable"},
        )
    except ValueError as exc:
        raise _http_from_upload_value_error(exc) from exc

    return {
        "status": "ok",
        "song_id": song_id,
        "duration_seconds": duration_seconds,
    }


@router.post("/songs/{song_id}/upload-cover")
def post_song_upload_cover(
    song_id: int,
    file: UploadFile = File(...),
    db=Depends(get_db),
    _owned_song: Song = Depends(require_song_owner),
):
    """Deprecated: song-level cover upload is removed in release-centric model."""
    logger.warning(
        "deprecated_song_cover_upload_endpoint_hit",
        extra={"song_id": int(song_id)},
    )
    raise HTTPException(
        status_code=410,
        detail="Song-level cover upload is deprecated. Use release cover upload.",
    )


@router.get("/api")
def root():
    return {"message": "Human Music Platform API"}


@router.get(
    "/tutorial",
    response_class=HTMLResponse,
    tags=["Onboarding"],
    summary="Beginner API tutorial",
    description="Quick onboarding page for stream -> payouts -> results flow.",
)
def tutorial():
    return """
    <html>
    <head>
      <title>Human Music API Tutorial</title>
      <style>
        body { font-family: Arial, sans-serif; max-width: 900px; margin: 32px auto; padding: 0 16px; line-height: 1.45; }
        .card { border: 1px solid #ddd; border-radius: 10px; padding: 16px; margin-bottom: 14px; }
        code { background: #f5f5f5; padding: 2px 6px; border-radius: 6px; }
      </style>
    </head>
    <body>
      <h1>Human Music Platform API Tutorial</h1>
      <p>Use this page with <code>/docs</code> open side-by-side.</p>
      <div class="card">
        <h2>1) Create stream</h2>
        <p><b>Production:</b> <code>POST /stream</code> with Bearer token (or dev-only legacy <code>X-User-Id</code>).</p>
        <p>Body example: <code>{"song_id":1,"duration":30}</code></p>
      </div>
      <div class="card">
        <h2>2) Generate payout preview</h2>
        <p><code>GET /payout/{user_id}</code> computes user-centric payout preview.</p>
        <p><code>GET /pool-distribution</code> provides global pool comparison baseline.</p>
      </div>
      <div class="card">
        <h2>3) View results</h2>
        <p><code>GET /compare/{user_id}</code> compares payout models.</p>
        <p><code>GET /artist-dashboard/{artist_id}</code> and analytics endpoints show artist outcomes.</p>
      </div>
      <div class="card">
        <h2>Dev mode tools</h2>
        <p><code>/dev/stream</code> and <code>/dev/events</code> are for local testing only.</p>
      </div>
    </body>
    </html>
    """


@router.post(
    "/artists/{artist_id}/songs",
    deprecated=True,
    summary="(Deprecated) Legacy artist multipart song ingestion",
    description=(
        "Deprecated legacy ingestion shortcut. This endpoint will be removed in a future version. "
        "Recommended flow: POST /songs -> POST /songs/{id}/upload-audio -> "
        "POST /songs/{id}/upload-cover -> PUT /songs/{id}/splits."
    ),
)
def upload_song(
    artist_id: int,
    title: str = Form(...),
    release_id: int | None = Form(default=None),
    file: UploadFile = File(...),
    _current_user: User = Depends(get_current_user),
    _owned_artist: Artist = Depends(require_artist_owner),
    db=Depends(get_db),
):
    """
    Deprecated legacy ingestion shortcut.
    This endpoint is deprecated and will be removed in a future version.
    Recommended flow: POST /songs -> upload-audio -> upload-cover -> splits.
    """
    timestamp_utc = datetime.utcnow().isoformat()
    logger.warning(
        "Using deprecated endpoint POST /artists/{artist_id}/songs",
        extra={
            "event": "legacy_song_upload_used",
            "user_id": int(_current_user.id),
            "artist_id": int(artist_id),
            "timestamp": timestamp_utc,
        },
    )
    service = SongIngestionService()
    try:
        song = service.create_song(
            db=db,
            artist_id=artist_id,
            title=title,
            file=file.file,
            splits=None,
            release_id=release_id,
            original_filename=file.filename,
            content_type=file.content_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "song_id": song.id,
        "title": song.title,
        "status": song.upload_status,
        "duration": song.duration_seconds,
    }


@router.post(
    "/stream",
    tags=["Streaming"],
    summary="Create production stream event",
    description=(
        "Production listening ingestion endpoint. Use Bearer auth; "
        "`X-User-Id` is a legacy fallback only when ENABLE_LEGACY_AUTH=true."
    ),
)
def stream_event(
    request: Request,
    user_id: int = Depends(get_listening_user_id),
    payload: StreamEventRequest = Body(
        ...,
        examples=[
            {
                "song_id": 1,
                "duration": 30,
                "session_id": 101,
                "idempotency_key": "strm-1-song-1-30s",
                "correlation_id": "mobile-playback-2026-04-21-001",
            }
        ],
    ),
    x_user_id_hint: Annotated[
        str | None,
        Header(
            alias="X-User-Id",
            description=(
                "Legacy listener id header. Prefer Bearer token. "
                "Only accepted when ENABLE_LEGACY_AUTH=true."
            ),
        ),
    ] = None,
    db=Depends(get_db),
):
    _ = x_user_id_hint
    _enforce_stream_rate_limit(request, user_id)
    song_id = payload.song_id
    duration = payload.duration
    session_id = payload.session_id
    idempotency_key = payload.idempotency_key
    correlation_id = payload.correlation_id

    if duration <= 0:
        raise HTTPException(status_code=400, detail="Invalid duration")

    listening_session_id: int | None = None
    if session_id is not None and str(session_id).strip() != "":
        try:
            listening_session_id = int(session_id)
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=400,
                detail="session_id must be a numeric listening session id",
            ) from exc

    return stream_service.process_stream(
        db,
        user_id,
        song_id,
        duration,
        listening_session_id=listening_session_id,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
    )


@router.post(
    "/stream/start-session",
    tags=["Streaming"],
    summary="Start production listening session",
    description="Creates a session id used by `/stream/checkpoint` and optional `/stream` linkage.",
)
def stream_start_session(
    request: Request,
    payload: StartSessionRequest,
    user_id: int = Depends(get_listening_user_id),
    db=Depends(get_db),
):
    _enforce_start_session_rate_limit(request, user_id)
    return process_start_listening_session(
        db,
        user_id=user_id,
        song_id=payload.song_id,
        discovery_request_id=(
            str(payload.discovery_request_id).strip()
            if payload.discovery_request_id is not None
            and str(payload.discovery_request_id).strip()
            else None
        ),
        discovery_section=(
            str(payload.discovery_section).strip()
            if payload.discovery_section is not None
            and str(payload.discovery_section).strip()
            else None
        ),
        discovery_position=(
            int(payload.discovery_position)
            if payload.discovery_position is not None
            else None
        ),
        source_type=payload.source_type,
        source_id=payload.source_id,
    )


@router.post(
    "/stream/checkpoint",
    tags=["Streaming"],
    summary="Write production playback checkpoint",
    description="Stores in-session playback progress for the authenticated listener.",
)
def stream_checkpoint(
    request: Request,
    user_id: int = Depends(get_listening_user_id),
    session_id: int = Body(...),
    song_id: int = Body(...),
    sequence: int = Body(...),
    position_seconds: int = Body(...),
    db=Depends(get_db),
):
    _enforce_checkpoint_rate_limit(request, user_id)
    return process_stream_checkpoint(
        db,
        user_id=user_id,
        session_id=session_id,
        song_id=song_id,
        sequence=sequence,
        position_seconds=position_seconds,
    )


@router.post(
    "/dev/stream",
    include_in_schema=(
        (os.getenv("APP_ENV") or os.getenv("ENV") or "").strip().lower()
        in {"dev", "development", "local", "test"}
    ),
    tags=["Dev Tools"],
    summary="Create dev stream event (internal helper)",
    description="Development-only internal helper backing the public `/dev/stream` endpoint.",
)
def _handle_dev_stream(
    db,
    user_id: int,
    song_id: int,
    duration: int,
    session_id: str | int | None = None,
    idempotency_key: str | None = None,
    correlation_id: str | None = None,
):
    listening_session_id: int | None = None
    if session_id is not None and str(session_id).strip() != "":
        try:
            listening_session_id = int(session_id)
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=400,
                detail="session_id must be a numeric listening session id",
            ) from exc

    logger.info(
        "dev_stream_used",
        extra={
            "user_id": user_id,
            "song_id": song_id,
            "duration": duration,
            "session_id": listening_session_id,
            "idempotency_key": idempotency_key,
            "correlation_id": correlation_id,
        },
    )

    return stream_service.process_stream(
        db=db,
        user_id=user_id,
        song_id=song_id,
        duration=duration,
        listening_session_id=listening_session_id,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
    )


@router.post(
    "/dev/stream",
    include_in_schema=(
        (os.getenv("APP_ENV") or os.getenv("ENV") or "").strip().lower()
        in {"dev", "development", "local", "test"}
    ),
    tags=["Dev Tools"],
    summary="Create dev stream event",
    description=(
        "Development-only stream endpoint. Supports explicit `user_id` and flexible body/query "
        "inputs for testing idempotency/session/correlation behavior."
    ),
)
def dev_stream_event(
    _dev_mode=Depends(require_dev_mode),
    payload: DevStreamRequest | dict | None = Body(
        default=None,
        examples=[
            {
                "user_id": 1,
                "song_id": 1,
                "duration": 30,
                "session_id": 101,
                "idempotency_key": "dev-user1-song1-30s",
                "correlation_id": "qa-run-42",
            }
        ],
    ),
    user_id_q: int | None = Query(default=None, alias="user_id"),
    song_id_q: int | None = Query(default=None, alias="song_id"),
    duration_q: int | None = Query(default=None, alias="duration"),
    session_id_q: str | int | None = Query(default=None, alias="session_id"),
    idempotency_key_q: str | None = Query(default=None, alias="idempotency_key"),
    correlation_id_q: str | None = Query(default=None, alias="correlation_id"),
    db=Depends(get_db),
):
    body = payload or {}

    def merged(name: str, query_value):
        # Body has precedence over query for local testing convenience.
        return body.get(name) if name in body else query_value

    user_id_raw = merged("user_id", user_id_q)
    song_id_raw = merged("song_id", song_id_q)
    duration_raw = merged("duration", duration_q)
    session_id_raw = merged("session_id", session_id_q)
    idempotency_key = merged("idempotency_key", idempotency_key_q)
    correlation_id = merged("correlation_id", correlation_id_q)

    if user_id_raw is None or song_id_raw is None or duration_raw is None:
        raise HTTPException(
            status_code=400,
            detail="user_id, song_id and duration are required (body or query)",
        )

    try:
        user_id = int(user_id_raw)
        song_id = int(song_id_raw)
        duration = int(duration_raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail="user_id, song_id and duration must be integers",
        ) from exc

    return _handle_dev_stream(
        db=db,
        user_id=user_id,
        song_id=song_id,
        duration=duration,
        session_id=session_id_raw,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
    )


@router.get(
    "/dev/stream",
    include_in_schema=(
        (os.getenv("APP_ENV") or os.getenv("ENV") or "").strip().lower()
        in {"dev", "development", "local", "test"}
    ),
    tags=["Dev Tools"],
    summary="Create dev stream event via query",
    description="Development-only convenience GET for quick manual testing.",
)
def dev_stream_get(
    user_id: int = Query(...),
    song_id: int = Query(...),
    duration: int = Query(...),
    session_id: str | None = Query(None),
    idempotency_key: str | None = Query(None),
    correlation_id: str | None = Query(None),
    db=Depends(get_db),
    _dev_mode=Depends(require_dev_mode),
):
    return _handle_dev_stream(
        db=db,
        user_id=user_id,
        song_id=song_id,
        duration=duration,
        session_id=session_id,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
    )


@router.get(
    "/dev/events",
    include_in_schema=(
        (os.getenv("APP_ENV") or os.getenv("ENV") or "").strip().lower()
        in {"dev", "development", "local", "test"}
    ),
    tags=["Dev Tools"],
    summary="Inspect recent listening events",
    description="Development-only event inspector with user/song/time filters.",
)
def dev_events(
    user_id: int | None = Query(default=None),
    song_id: int | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    only_valid: bool = Query(default=False),
    since_minutes: int = Query(default=60, ge=1, le=24 * 60),
    db=Depends(get_db),
    _dev_mode=Depends(require_dev_mode),
):
    since_at = datetime.utcnow() - timedelta(minutes=int(since_minutes))

    query = db.query(ListeningEvent).filter(ListeningEvent.created_at >= since_at)
    if user_id is not None:
        query = query.filter(ListeningEvent.user_id == int(user_id))
    if song_id is not None:
        query = query.filter(ListeningEvent.song_id == int(song_id))
    if only_valid:
        query = query.filter(ListeningEvent.is_valid.is_(True))

    rows = (
        query.order_by(ListeningEvent.created_at.desc())
        .limit(int(limit))
        .all()
    )

    logger.info(
        "dev_events_viewed",
        extra={
            "user_id": user_id,
            "song_id": song_id,
            "limit": int(limit),
            "only_valid": bool(only_valid),
            "since_minutes": int(since_minutes),
        },
    )

    return [
        {
            "event_id": int(e.id),
            "user_id": int(e.user_id) if e.user_id is not None else None,
            "song_id": int(e.song_id) if e.song_id is not None else None,
            "is_valid": bool(e.is_valid),
            "validation_reason": e.validation_reason,
            "duration": float(e.duration) if e.duration is not None else None,
            "validated_duration": (
                float(e.validated_duration) if e.validated_duration is not None else None
            ),
            "weight": float(e.weight) if e.weight is not None else None,
            "session_id": int(e.session_id) if e.session_id is not None else None,
            "idempotency_key": e.idempotency_key,
            "correlation_id": e.correlation_id,
            "created_at": e.created_at.isoformat() if e.created_at is not None else None,
        }
        for e in rows
    ]


@router.get(
    "/payout/{user_id}",
    tags=["Payouts"],
    summary="Preview payout distribution for one fan",
    description="Computes user-centric payout preview by song and expanded artist allocation.",
)
def get_payout(
    user_id: int,
    _authorized_user: User = Depends(require_self_or_admin),
):
    songs = calculate_user_distribution(user_id)
    db = SessionLocal()
    try:
        artists = expand_song_distribution_to_artists(
            db,
            [{"song_id": row["song_id"], "cents": row["cents"]} for row in songs],
        )
    finally:
        db.close()

    songs_total_cents = sum(int(row.get("cents", 0) or 0) for row in songs)
    artists_total_cents = sum(int(row.get("cents", 0) or 0) for row in artists)
    if songs_total_cents != artists_total_cents:
        raise HTTPException(
            status_code=500,
            detail=(
                "Distribution preview conservation error: "
                f"songs={songs_total_cents}, artists={artists_total_cents}"
            ),
        )
    meta = {
        "total_cents": songs_total_cents,
        "currency": "EUR",
        "mode": "user-centric-preview",
    }
    return {"meta": meta, "songs": songs, "artists": artists}


@router.get(
    "/pool-distribution",
    tags=["Payouts"],
    summary="Preview global pool distribution",
    description="Returns global/pool model distribution for ecosystem-level comparison.",
)
def get_pool_distribution():
    return calculate_global_distribution()


@router.put("/songs/{song_id}/splits")
def put_song_splits(
    song_id: int,
    body: SetSongSplitsBody,
    db=Depends(get_db),
    song: Song = Depends(require_song_owner),
):
    """
    Replace all ``SongArtistSplit`` rows for a song. Validation runs before save.

    This is the supported application entry point for creating/updating splits.
    """
    if str(song.upload_status or "").strip().lower() == "ready":
        raise HTTPException(
            status_code=400,
            detail="splits_locked",
        )
    rows = [r.model_dump() for r in body.splits]
    try:
        created = set_splits_for_song(db, song_id, rows)
    except SplitValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {
        "song_id": song_id,
        "splits": [
            {"id": c.id, "artist_id": c.artist_id, "share": c.share}
            for c in created
        ],
    }


@router.get(
    "/compare/{user_id}",
    tags=["Analytics"],
    summary="Compare user-centric and global models",
    description="Side-by-side model comparison for one user id.",
)
def compare(
    user_id: int,
    _authorized_user: User = Depends(require_self_or_admin),
):
    return compare_models(user_id)


@router.get(
    "/artist/{artist_id}/streams",
    tags=["Analytics"],
    summary="Get artist stream timeline",
)
def artist_streams(
    artist_id: int,
    range: str = Query(..., description="Time range preset"),
    song_id: Optional[int] = Query(None, description="Optional song filter"),
    _owned_artist: Artist = Depends(require_artist_owner),
):
    return get_artist_streams_over_time(
        artist_id=artist_id,
        range=range,
        song_id=song_id,
    )


@router.get(
    "/artist/{artist_id}/top-songs",
    tags=["Analytics"],
    summary="Get artist top songs",
)
def artist_top_songs(
    artist_id: int,
    range: str = Query(..., description="Time range preset"),
    _owned_artist: Artist = Depends(require_artist_owner),
):
    return get_artist_top_songs(
        artist_id=artist_id,
        range=range,
    )


@router.get(
    "/artist/{artist_id}/top-fans",
    tags=["Analytics"],
    summary="Get artist top fans",
)
def artist_top_fans(
    artist_id: int,
    range: str = Query(..., description="Time range preset"),
    _owned_artist: Artist = Depends(require_artist_owner),
):
    return get_artist_top_fans(
        artist_id=artist_id,
        range=range,
    )


@router.get(
    "/artist/{artist_id}/insights",
    tags=["Analytics"],
    summary="Get artist narrative insights",
)
def artist_insights(
    artist_id: int,
    range: str = Query("last_30_days", description="Time range preset"),
    _owned_artist: Artist = Depends(require_artist_owner),
):
    return get_artist_insights(artist_id=artist_id, range=range)


@router.get("/dashboard/{user_id}", response_class=HTMLResponse)
def dashboard(
    user_id: int,
    _authorized_user: User = Depends(require_self_or_admin),
):
    data = compare_models(user_id)

    html = f"""
    <html>
    <head>
        <title>Music Payout Dashboard</title>
        <style>
            body {{
                font-family: Arial;
                padding: 40px;
            }}
            .card {{
                border: 1px solid #ccc;
                padding: 20px;
                margin-bottom: 20px;
                border-radius: 10px;
            }}
        </style>
    </head>
    <body>
        <h1>User {user_id} - Payout Comparison</h1>
    """

    for item in data["comparison"]:
        html += f"""
        <div class="card">
            <h2>Song {item['song_id']}</h2>
            <p><b>Your Model:</b> {item.get('user_payout', 0)} €</p>
            <p><b>Spotify Model:</b> {item.get('pool_amount', 0)} €</p>
            <p><b>Difference:</b> {round((item.get('user_payout') or 0) - (item.get('pool_amount') or 0), 2)} €</p>
        </div>
        """

    html += "</body></html>"

    return html


@router.get("/artist-dashboard/{artist_id}", response_class=HTMLResponse)
def artist_dashboard(
    artist_id: int,
    _owned_artist: Artist = Depends(require_artist_owner),
):
    data = get_artist_dashboard(artist_id)
    diff = data.get("difference")
    diff_value = float(diff or 0)
    diff_sign = "+" if diff_value > 0 else ""
    show_toggle = diff is not None and diff < 0

    # Always first day of next calendar month.
    today = date.today()
    if today.month == 12:
        next_payout_date = date(today.year + 1, 1, 1)
    else:
        next_payout_date = date(today.year, today.month + 1, 1)

    last_payouts_html = ""
    for payout in data.get("last_payouts", []):
        _pd = payout.get("payout_date")
        payout_date = str(_pd) if _pd is not None else "—"
        payout_amount = round(float(payout.get("amount") or 0), 2)
        last_payouts_html += f"""
        <div style="margin-bottom:8px;">{payout_date} — {payout_amount} €</div>
        """
    if not last_payouts_html:
        last_payouts_html = '<p class="ah-muted" style="margin:0;">No paid payouts yet.</p>'

    pending_html = ""
    pending_value = float(data.get("pending") or 0)
    if pending_value > 0:
        pending_html = f"<p><b>Pending payout:</b> {round(pending_value, 2)} €</p>"
    accrued_html = ""
    accrued_value = float(data.get("accrued") or 0)
    if accrued_value > 0:
        accrued_html = (
            f"<p><b>Accrued (not yet on-chain):</b> {round(accrued_value, 2)} €</p>"
        )
    failed_html = ""
    failed_value = float(data.get("failed_settlement") or 0)
    if failed_value > 0:
        failed_html = (
            f"<p><b>Settlement failed (review):</b> {round(failed_value, 2)} €</p>"
        )

    negative_diff_message = ""
    if diff_value < 0:
        negative_diff_message = """
        <p style="margin-top:12px; margin-bottom:16px; line-height:1.6;">
            Your audience is supporting you directly.<br>
            You are earning what's fair while contributing to a more balanced and sustainable music ecosystem.<br><br>
            Thank you for inspiring the world.
        </p>
        """

    toggle_html = ""
    if show_toggle:
        toggle_html = f"""
        <button type="button" class="ah-btn" onclick="toggleDetails()">
            See how this compares to traditional streaming platforms
        </button>
        <div id="details" class="ah-toggle-panel" style="display:none;">
            <p><b>Global model estimate:</b> {data['spotify_total']} €</p>
            <p><b>Difference:</b> {diff_sign}{round(diff_value, 2)} € vs global model</p>
            <p class="ah-lead" style="margin-top:12px;">
                Comparison based on payout earnings vs global pool model (ex: Spotify, Apple Music, Amazon, YouTube, etc)
            </p>
        </div>
        """

    html = f"""
    {_artist_hub_html_head(f"Artist {artist_id} Dashboard")}
    <body class="artist-hub">
    <div class="artist-hub-inner">
        <h1>Artist {artist_id} Dashboard</h1>
        {_artist_hub_nav(artist_id, "overview")}

        <div id="heroInsight" class="ah-card ah-card--hero"></div>

        <section class="ah-card ah-card--earnings">
            <h2>💸 Earnings</h2>
            <p class="ah-lead">
                Ledger from <code>payout_lines</code>. <b>Paid</b> = on-chain confirmed;
                <b>Accrued</b> = finalized in books, settlement not confirmed yet.
            </p>
            <p><b>Total earnings:</b> {data['total']} €</p>
            <p><b>Paid (on-chain):</b> {data['paid']} €</p>
            {accrued_html}
            {failed_html}
            <h3 style="margin-top:16px; margin-bottom:10px;">Last on-chain payouts</h3>
            {last_payouts_html}
            <p style="margin-top:10px;"><a class="ah-inline-link" href="{_next_app_base_url()}/studio/payouts">View all payouts (Studio) →</a></p>
            <p style="margin-top:16px;"><b>Next payout:</b> {next_payout_date.isoformat()}</p>
            {pending_html}
        </section>

        <section class="ah-card ah-card--accent">
            <h2>📊 Global Model Comparison</h2>
            {negative_diff_message}
            {""
            if diff_value < 0
            else f'''
            <p><b>Global model estimate:</b> {data['spotify_total']} €</p>
            <p><b>You earned {diff_sign}{round(diff_value, 2)} €</b> more than on other platforms!</p>
            <p class="ah-lead" style="margin-top:12px;">
                Comparison based on payout earnings vs global pool model (ex: Spotify, Apple Music, Amazon, YouTube, etc)
            </p>
            '''
            }
            {toggle_html}
        </section>

        <script>
        function toggleDetails() {{
            var x = document.getElementById("details");
            if (!x) return;
            if (x.style.display === "none") {{
                x.style.display = "block";
            }} else {{
                x.style.display = "none";
            }}
        }}

        function escapeHtmlInsight(s) {{
            if (s === null || s === undefined) return "";
            return String(s)
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;");
        }}

        function heroInsightSubtext(story) {{
            if (!story || !story.data || typeof story.data !== "object") return "";
            var d = story.data;
            var t = story.type || "";
            if (t === "fan_engagement") {{
                var u = escapeHtmlInsight(d.username != null ? d.username : "");
                var song = escapeHtmlInsight(d.song_title != null ? d.song_title : "");
                if (u || song) {{
                    return "Fan: " + (u || "—") + " — Song: " + (song || "—");
                }}
            }}
            if (t === "early_listeners" && d.listeners != null && d.listeners !== "") {{
                return escapeHtmlInsight(String(d.listeners)) + " listeners discovered your music";
            }}
            if (t === "top_fan_week") {{
                var u2 = escapeHtmlInsight(d.username != null ? d.username : "");
                if (u2 && d.streams != null && d.streams !== "") {{
                    return "Fan: " + u2 + " — " + escapeHtmlInsight(String(d.streams)) + " listens in the last 7 days";
                }}
                if (u2) return "Fan: " + u2;
            }}
            if (t === "fans_reached" && d.listeners != null && d.listeners !== "") {{
                return escapeHtmlInsight(String(d.listeners)) + " unique listeners in the last 30 days";
            }}
            return "";
        }}

        (async function loadHeroInsight() {{
            var el = document.getElementById("heroInsight");
            if (!el) return;
            try {{
                var res = await fetch(`/artist/{artist_id}/insights?range=${{encodeURIComponent("last_30_days")}}`);
                if (!res.ok) return;
                var json = await res.json();
                var stories = json.stories;
                if (!Array.isArray(stories) || stories.length === 0) return;
                var story = stories[0];
                if (!story || typeof story.message !== "string") return;
                var msg = escapeHtmlInsight(story.message);
                var sub = heroInsightSubtext(story);
                el.style.display = "block";
                el.innerHTML =
                    '<h2 class="ah-hero-title">🔥 Insight</h2>' +
                    '<p class="ah-hero-msg">' + msg + "</p>" +
                    (sub
                        ? '<p class="ah-hero-sub">' + sub + "</p>"
                        : "");
            }} catch (e) {{
                /* keep hidden */
            }}
        }})();
        </script>
    </div>
    </body></html>
    """

    return html


@router.post("/artist/{artist_id}/payout-method")
def post_artist_payout_method(
    artist_id: int,
    payout_method: str = Form(...),
    payout_wallet_address: str = Form(""),
    payout_bank_info: str = Form(""),
    _reject_impersonation: None = Depends(require_non_impersonation),
    _owned_artist: Artist = Depends(require_artist_owner),
):
    raw_method = payout_method.strip().lower()
    if raw_method not in ALLOWED_PAYOUT_METHODS:
        raise HTTPException(status_code=422, detail="Invalid payout_method")

    wallet = (payout_wallet_address or "").strip()
    bank = (payout_bank_info or "").strip()

    if len(wallet) > MAX_PAYOUT_TEXT_LEN or len(bank) > MAX_PAYOUT_TEXT_LEN:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Wallet and bank fields must be at most {MAX_PAYOUT_TEXT_LEN} "
                "characters"
            ),
        )

    w_store: Optional[str] = None
    b_store: Optional[str] = None

    if raw_method == "crypto":
        if not wallet:
            raise HTTPException(
                status_code=422,
                detail="Wallet address is required when payout_method is crypto",
            )
        w_store = wallet
        b_store = None
    elif raw_method == "bank":
        if not bank:
            raise HTTPException(
                status_code=422,
                detail="Bank details are required when payout_method is bank",
            )
        w_store = None
        b_store = bank
    else:
        w_store = None
        b_store = None

    db = SessionLocal()
    try:
        artist = db.query(Artist).filter(Artist.id == artist_id).first()
        if artist is None:
            raise HTTPException(status_code=404, detail="Artist not found")
        artist.payout_method = raw_method
        artist.payout_wallet_address = w_store
        artist.payout_bank_info = b_store
        db.commit()
        selected = (artist.payout_method or "none").strip().lower()
        if selected not in ("crypto", "bank", "none"):
            selected = "none"
        return {
            "success": True,
            "payout_method": {
                "selected": selected,
                "wallet_address": artist.payout_wallet_address,
                "bank_configured": bool((artist.payout_bank_info or "").strip()),
            },
        }
    finally:
        db.close()


@router.get("/admin/payouts")
def get_admin_payouts(
    status: Optional[str] = Query(None, description="Filter by payout status"),
    artist_id: Optional[int] = Query(None, description="Filter by artist id"),
    artist_name: Optional[str] = Query(None, description="Filter by artist name"),
    limit: int = Query(50, ge=1, le=500, description="Max rows to return"),
    _admin_user: User = Depends(require_admin_user),
):
    name_artist_ids = None
    db = SessionLocal()
    try:
        if artist_name and artist_name.strip():
            cleaned_name = artist_name.strip()
            matching_artists = (
                db.query(Artist.id)
                .filter(
                    func.lower(Artist.name).like(f"%{cleaned_name.lower()}%"),
                )
                .all()
            )
            name_artist_ids = [int(a.id) for a in matching_artists]
        if name_artist_ids is not None and len(name_artist_ids) == 0:
            groups = []
        else:
            groups = fetch_admin_ledger_groups(
                db,
                status=status,
                artist_id=artist_id,
                artist_ids_from_name=name_artist_ids,
                limit=limit,
            )
    finally:
        db.close()

    out = []
    for g in groups:
        created = g.created_at or g.period_end_at
        tx_id = (
            str(g.algorand_tx_id).strip()
            if g.algorand_tx_id and str(g.algorand_tx_id).strip()
            else None
        )
        out.append(
            {
                "id": synthetic_ledger_group_id(g.batch_id, g.artist_id),
                "batch_id": g.batch_id,
                "batch_status": g.batch_status,
                "distinct_users": g.distinct_users,
                "user_id": None,
                "artist_id": g.artist_id,
                "artist_name": g.artist_name,
                "amount": round(float(g.amount_cents) / 100.0, 2),
                "ui_status": g.ui_status,
                "status": g.ui_status,
                "wallet": g.destination_wallet,
                "destination_wallet": g.destination_wallet,
                "tx": {
                    "tx_id": tx_id,
                    "explorer_url": lora_transaction_explorer_url(tx_id),
                },
                "created": created.isoformat() if created is not None else None,
                "created_at": created.isoformat() if created is not None else None,
                "attempts": g.attempt_count,
                "attempt_count": g.attempt_count,
                "failure_reason": g.failure_reason,
                "algorand_tx_id": tx_id,
                "tx_id": tx_id,
            }
        )
    return out


@router.post("/admin/settle-batch/{batch_id}")
def post_admin_settle_batch(
    batch_id: int,
    _reject_impersonation: None = Depends(require_non_impersonation),
    _admin_user: User = Depends(require_admin_user),
):
    """Run V2 on-chain settlement for all artists in a finalized/posted batch."""
    try:
        return process_batch_settlement(batch_id, admin_user_id=int(_admin_user.id))
    except BatchLockContentionError as e:
        raise HTTPException(
            status_code=409,
            detail=str(e) or "Batch is currently being processed by another admin",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/action-logs")
def get_admin_action_logs(
    limit: int = Query(50, ge=1, le=500, description="Max logs to return"),
    _admin_user: User = Depends(require_admin_user),
):
    db = SessionLocal()
    try:
        rows = (
            db.query(AdminActionLog, User.email)
            .outerjoin(User, User.id == AdminActionLog.admin_user_id)
            .order_by(AdminActionLog.created_at.desc(), AdminActionLog.id.desc())
            .limit(int(limit))
            .all()
        )
    finally:
        db.close()
    return [
        {
            "admin_user_id": int(log.admin_user_id),
            "admin_user_email": str(email).strip() if email else None,
            "action_type": str(log.action_type),
            "target_id": int(log.target_id),
            "created_at": log.created_at.isoformat() if log.created_at is not None else None,
            "metadata": log.metadata_json,
        }
        for log, email in rows
    ]


@router.post("/admin/retry-payout/{payout_id}")
def post_admin_retry_payout(
    payout_id: int,
    status: Optional[str] = Query(None),
    artist_id: Optional[str] = Query(None),
    artist_name: Optional[str] = Query(None),
    limit: Optional[int] = Query(None, ge=1, le=500),
    _reject_impersonation: None = Depends(require_non_impersonation),
    _admin_user: User = Depends(require_admin_user),
):
    raise HTTPException(
        status_code=501,
        detail=(
            "Legacy per-row payout retry is not available for the V2 ledger "
            "(payout_lines / payout_batches). Use batch posting workflows instead."
        ),
    )


@router.post("/admin/retry-batch/{batch_id}")
def post_admin_retry_batch(
    batch_id: int,
    _reject_impersonation: None = Depends(require_non_impersonation),
    _admin_user: User = Depends(require_admin_user),
):
    """Retry only failed payout settlements in one batch."""
    try:
        return retry_failed_settlements_for_batch(
            batch_id, admin_user_id=int(_admin_user.id)
        )
    except BatchLockContentionError as e:
        raise HTTPException(
            status_code=409,
            detail=str(e) or "Batch is currently being processed by another admin",
        )
    except (RuntimeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/artist-payouts/{artist_id}")
def redirect_artist_payouts_to_studio(
    artist_id: int,
    _owned_artist: Artist = Depends(require_artist_owner),
):
    """Legacy HTML payouts page removed; bookmarks hit Studio."""
    return RedirectResponse(
        url=f"{_next_app_base_url()}/studio/payouts",
        status_code=302,
    )


@router.get("/artist-analytics/{artist_id}")
def redirect_artist_analytics_to_studio(
    artist_id: int,
    _owned_artist: Artist = Depends(require_artist_owner),
):
    """Legacy HTML analytics removed; bookmarks hit Studio."""
    return RedirectResponse(
        url=f"{_next_app_base_url()}/studio/analytics",
        status_code=302,
    )