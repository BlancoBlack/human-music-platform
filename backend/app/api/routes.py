import json
import logging
import math
import os
import threading
import time
from collections import deque
from datetime import date, datetime, timedelta
from typing import Literal, Optional
from urllib.parse import quote, urlencode

from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import desc, func

# 🔥 nuevo import (service)
from app.api.deps import get_listening_user_id, require_non_impersonation
from app.core.database import SessionLocal, get_db
from app.models.artist import Artist
from app.models.listening_event import ListeningEvent
from app.models.song import Song
from app.models.song_credit_entry import SongCreditEntry
from app.models.song_featured_artist import SongFeaturedArtist
from app.models.song_media_asset import (
    SONG_MEDIA_KIND_COVER_ART,
    SONG_MEDIA_KIND_MASTER_AUDIO,
    SongMediaAsset,
)
from app.models.user import User
from app.services.payout_service import calculate_user_distribution
from app.services.payout_ledger_ui_service import (
    admin_ledger_group_counts,
    artist_batch_history,
    artist_ledger_bucket_cents,
    fetch_admin_ledger_groups,
    synthetic_ledger_group_id,
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
    upload_song_cover_art,
    upload_song_master_audio,
)
from app.services.song_metadata_service import create_song_with_metadata
from app.services.song_split_validation import SplitValidationError
from app.workers.settlement_worker import process_batch_settlement

logger = logging.getLogger(__name__)

# Lora explorer (AlgoExplorer deprecated)
# NETWORK controls testnet vs mainnet
NETWORK = os.getenv("NETWORK", "testnet")
if NETWORK == "mainnet":
    EXPLORER_BASE_URL = "https://lora.algokit.io/mainnet"
else:
    EXPLORER_BASE_URL = "https://lora.algokit.io/testnet"

router = APIRouter()

stream_service = StreamService()

ADMIN_KEY = "dev-secret"


def _next_app_base_url() -> str:
    return os.getenv("NEXT_APP_BASE_URL", "http://localhost:3000").rstrip("/")


def _artist_upload_href(artist_id: int) -> str:
    return f"{_next_app_base_url()}/artist-upload?artist_id={artist_id}"


def _artist_catalog_href(artist_id: int) -> str:
    return f"{_next_app_base_url()}/artist-catalog?artist_id={artist_id}"


# Shared dark UI for artist HTML pages (dashboard / analytics / payouts).
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
.ah-fan-item {
  margin-bottom: 0.75rem;
  padding: 0.75rem 1rem;
  border: 1px solid #27272a;
  border-radius: 0.5rem;
  background: #141416;
  color: #d4d4d8;
}
.ah-payout-row td:last-child { color: #a1a1aa; font-size: 0.8rem; }
#heroInsight { display: none; }
.ah-hero-title { margin-top: 0; }
.ah-hero-msg { font-size: 1.1rem; margin: 0.5rem 0; line-height: 1.5; color: #fafafa; }
.ah-hero-sub { font-size: 0.9rem; color: #a1a1aa; margin-top: 0.75rem; margin-bottom: 0; }
.ah-warn { color: #fbbf24; }
.artist-hub b { color: #fafafa; font-weight: 600; }
.artist-hub ol { color: #d4d4d8; }
.artist-hub ol li { margin-bottom: 0.5rem; }
.ah-chart-canvas { max-width: 100%; height: auto !important; }
.ah-range-row { display: flex; gap: 0.65rem; align-items: center; margin-bottom: 0.75rem; flex-wrap: wrap; }
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
    """active: overview | analytics | payouts"""
    items: list[tuple[str, str, str]] = [
        ("overview", f"/artist-dashboard/{artist_id}", "Overview"),
        ("analytics", f"/artist-analytics/{artist_id}", "Analytics"),
        ("payouts", f"/artist-payouts/{artist_id}", "Payouts"),
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


def _payout_status_display(status: Optional[str]) -> str:
    if not status:
        return "—"
    lowered = status.strip().lower()
    if lowered in ("paid", "pending", "processing", "accrued", "failed"):
        return lowered
    return _html_escape(status.strip())


def _artist_payout_method_banner(artist: Artist) -> str:
    method = (artist.payout_method or "none").strip().lower()
    wallet = (artist.payout_wallet_address or "").strip()
    bank = (artist.payout_bank_info or "").strip()

    if method not in ALLOWED_PAYOUT_METHODS:
        return (
            '<p class="ah-warn" style="margin:0;">'
            "⚠️ Payout method incomplete"
            "</p>"
        )

    if method == "none":
        return (
            '<p class="ah-warn" style="margin:0;">'
            "⚠️ No payout method configured"
            "</p>"
        )

    if method == "crypto":
        if not wallet:
            return (
                '<p class="ah-warn" style="margin:0;">'
                "⚠️ Payout method incomplete"
                "</p>"
            )
        return (
            "<p style='margin:0 0 8px 0;'><b>💸 Payout method:</b> Crypto (Algorand)</p>"
            f"<p style='margin:0;'><b>Address:</b> {_html_escape(wallet)}</p>"
        )

    if method == "bank":
        if not bank:
            return (
                '<p class="ah-warn" style="margin:0;">'
                "⚠️ Payout method incomplete"
                "</p>"
            )
        return (
            "<p style='margin:0 0 8px 0;'><b>🏦 Payout method:</b> Bank transfer</p>"
            f"<p style='margin:0;'><b>Details:</b> {_html_escape(bank)}</p>"
        )

    return (
        '<p class="ah-warn" style="margin:0;">'
        "⚠️ Payout method incomplete"
        "</p>"
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
    "musician",
    "mix engineer",
    "mastering engineer",
    "producer",
    "studio",
]


class CreateSongCreditBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=512)
    role: SongCreditRole


class CreateSongBody(BaseModel):
    title: str = Field(..., min_length=1)
    artist_id: int = Field(..., description="Primary (release) artist")
    featured_artist_ids: list[int] = Field(default_factory=list, max_length=20)
    credits: list[CreateSongCreditBody] = Field(default_factory=list, max_length=20)


class StartSessionRequest(BaseModel):
    song_id: int


@router.post("/songs")
def post_create_song(body: CreateSongBody, db=Depends(get_db)):
    """
    Create a song with title, primary artist, optional featuring artists and credits.
    Does not upload audio or set splits; those use other endpoints.
    """
    try:
        song = create_song_with_metadata(
            db,
            title=body.title,
            artist_id=body.artist_id,
            featured_artist_ids=body.featured_artist_ids,
            credits=[c.model_dump() for c in body.credits],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "song_id": song.id,
        "title": song.title,
        "artist_id": song.artist_id,
        "featured_artist_ids": list(body.featured_artist_ids),
        "credits": [c.model_dump() for c in body.credits],
    }


@router.get("/songs/{song_id}")
def get_song(song_id: int, db=Depends(get_db)):
    """
    Song detail for upload wizard: status, duration, media flags, metadata joins.
    ``cover_url`` is a path relative to the API host (static ``/uploads`` mount).
    """
    song = db.query(Song).filter(Song.id == int(song_id)).first()
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
    cover = (
        db.query(SongMediaAsset)
        .filter(
            SongMediaAsset.song_id == int(song_id),
            SongMediaAsset.kind == SONG_MEDIA_KIND_COVER_ART,
        )
        .first()
    )
    has_master_audio = master is not None
    has_cover_art = cover is not None
    cover_url = None
    if cover is not None and cover.file_path:
        p = str(cover.file_path).replace("\\", "/").lstrip("/")
        cover_url = f"/{p}"

    return {
        "id": song.id,
        "title": song.title,
        "artist_id": song.artist_id,
        "upload_status": song.upload_status,
        "duration_seconds": song.duration_seconds,
        "featured_artist_ids": featured_artist_ids,
        "credits": credits,
        "has_master_audio": has_master_audio,
        "has_cover_art": has_cover_art,
        "cover_url": cover_url,
    }


_MAX_ARTIST_SEARCH_Q_LEN = 128


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
        "artists": [{"id": int(a.id), "name": a.name} for a in rows],
    }


@router.get("/artists/{artist_id}")
def get_artist(artist_id: int, db=Depends(get_db)):
    """Public artist record for clients (e.g. upload wizard)."""
    artist = _get_public_artist_or_404(db, artist_id)
    return {"id": artist.id, "name": artist.name}


def _public_media_url_from_stored_path(file_path: str | None) -> str | None:
    """Same URL shape as ``cover_url`` / static ``/uploads`` mount in ``GET /songs/{id}``."""
    if file_path is None or not str(file_path).strip():
        return None
    p = str(file_path).replace("\\", "/").lstrip("/")
    return f"/{p}"


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
        .filter(Song.artist_id == int(artist_id))
        .order_by(desc(Song.created_at))
        .limit(int(limit))
        .all()
    )
    if not songs:
        return {"songs": []}

    song_ids = [int(s.id) for s in songs]
    assets = (
        db.query(SongMediaAsset)
        .filter(SongMediaAsset.song_id.in_(song_ids))
        .all()
    )
    master_by_sid: dict[int, SongMediaAsset] = {}
    cover_by_sid: dict[int, SongMediaAsset] = {}
    for asset in assets:
        sid = int(asset.song_id)
        if asset.kind == SONG_MEDIA_KIND_MASTER_AUDIO:
            master_by_sid[sid] = asset
        elif asset.kind == SONG_MEDIA_KIND_COVER_ART:
            cover_by_sid[sid] = asset

    payload = []
    for song in songs:
        sid = int(song.id)
        master = master_by_sid.get(sid)
        cover = cover_by_sid.get(sid)
        has_master_audio = master is not None
        cover_url = _public_media_url_from_stored_path(
            cover.file_path if cover else None,
        )
        audio_url = _public_media_url_from_stored_path(
            master.file_path if master else None,
        )
        upload_status = str(song.upload_status or "")
        playable = has_master_audio and upload_status == "ready"
        payload.append(
            {
                "id": sid,
                "title": song.title,
                "artist_id": int(song.artist_id),
                "upload_status": upload_status,
                "duration_seconds": song.duration_seconds,
                "cover_url": cover_url,
                "audio_url": audio_url,
                "has_master_audio": has_master_audio,
                "playable": playable,
            }
        )
    return {"songs": payload}


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
):
    """Upload cover art (JPEG/PNG) for an existing song."""
    try:
        upload_song_cover_art(
            db,
            song_id,
            file.file,
            original_filename=file.filename,
            content_type=file.content_type,
        )
    except CoverResolutionInvalidError:
        return JSONResponse(
            status_code=400,
            content={"error": "cover_resolution_invalid"},
        )
    except ValueError as exc:
        raise _http_from_upload_value_error(exc) from exc

    return {"status": "ok", "song_id": song_id}


@router.get("/api")
def root():
    return {"message": "Human Music Platform API"}


@router.post("/artists/{artist_id}/songs")
def upload_song(
    artist_id: int,
    title: str = Form(...),
    file: UploadFile = File(...),
    db=Depends(get_db),
):
    """
    Upload a new song for an artist
    """
    service = SongIngestionService()
    try:
        song = service.create_song(
            db=db,
            artist_id=artist_id,
            title=title,
            file=file.file,
            splits=None,
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


@router.post("/stream")
def stream_event(
    request: Request,
    user_id: int = Depends(get_listening_user_id),
    song_id: int = Body(...),
    duration: int = Body(...),
    session_id: str | int | None = Body(default=None),
    idempotency_key: str | None = Body(default=None),
    correlation_id: str | None = Body(default=None),
    db=Depends(get_db),
):
    _enforce_stream_rate_limit(request, user_id)

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


@router.post("/stream/start-session")
def stream_start_session(
    request: Request,
    payload: StartSessionRequest,
    user_id: int = Depends(get_listening_user_id),
    db=Depends(get_db),
):
    _enforce_start_session_rate_limit(request, user_id)
    return process_start_listening_session(
        db, user_id=user_id, song_id=payload.song_id
    )


@router.post("/stream/checkpoint")
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
)
def dev_stream_event(
    _dev_mode=Depends(require_dev_mode),
    payload: dict | None = Body(default=None),
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


@router.get("/payout/{user_id}")
def get_payout(user_id: int):
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


@router.get("/pool-distribution")
def get_pool_distribution():
    return calculate_global_distribution()


@router.put("/songs/{song_id}/splits")
def put_song_splits(song_id: int, body: SetSongSplitsBody):
    """
    Replace all ``SongArtistSplit`` rows for a song. Validation runs before save.

    This is the supported application entry point for creating/updating splits.
    """
    rows = [r.model_dump() for r in body.splits]
    db = SessionLocal()
    try:
        created = set_splits_for_song(db, song_id, rows)
    except SplitValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        db.close()

    return {
        "song_id": song_id,
        "splits": [
            {"id": c.id, "artist_id": c.artist_id, "share": c.share}
            for c in created
        ],
    }


@router.get("/compare/{user_id}")
def compare(user_id: int):
    return compare_models(user_id)


@router.get("/artist/{artist_id}/streams")
def artist_streams(
    artist_id: int,
    range: str = Query(..., description="Time range preset"),
    song_id: Optional[int] = Query(None, description="Optional song filter"),
):
    db = SessionLocal()
    try:
        _get_public_artist_or_404(db, artist_id)
    finally:
        db.close()
    return get_artist_streams_over_time(
        artist_id=artist_id,
        range=range,
        song_id=song_id,
    )


@router.get("/artist/{artist_id}/top-songs")
def artist_top_songs(
    artist_id: int,
    range: str = Query(..., description="Time range preset"),
):
    db = SessionLocal()
    try:
        _get_public_artist_or_404(db, artist_id)
    finally:
        db.close()
    return get_artist_top_songs(
        artist_id=artist_id,
        range=range,
    )


@router.get("/artist/{artist_id}/top-fans")
def artist_top_fans(
    artist_id: int,
    range: str = Query(..., description="Time range preset"),
):
    db = SessionLocal()
    try:
        _get_public_artist_or_404(db, artist_id)
    finally:
        db.close()
    return get_artist_top_fans(
        artist_id=artist_id,
        range=range,
    )


@router.get("/artist/{artist_id}/insights")
def artist_insights(
    artist_id: int,
    range: str = Query("last_30_days", description="Time range preset"),
):
    db = SessionLocal()
    try:
        _get_public_artist_or_404(db, artist_id)
    finally:
        db.close()
    return get_artist_insights(artist_id=artist_id, range=range)


@router.get("/dashboard/{user_id}", response_class=HTMLResponse)
def dashboard(user_id: int):
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
def artist_dashboard(artist_id: int):
    guard_db = SessionLocal()
    try:
        _get_public_artist_or_404(guard_db, artist_id)
    finally:
        guard_db.close()

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
            <p style="margin-top:10px;"><a class="ah-inline-link" href="/artist-payouts/{artist_id}">View all payouts →</a></p>
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
    admin_key: str = Query(..., description="MVP shared secret; compare to ADMIN_KEY"),
    payout_method: str = Form(...),
    payout_wallet_address: str = Form(""),
    payout_bank_info: str = Form(""),
    _reject_impersonation: None = Depends(require_non_impersonation),
):
    if admin_key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")

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
    finally:
        db.close()

    return RedirectResponse(
        url=f"/artist-payouts/{artist_id}",
        status_code=303,
    )


@router.get("/admin/payouts")
def get_admin_payouts(
    admin_key: str = Query(..., description="MVP shared secret; compare to ADMIN_KEY"),
    status: Optional[str] = Query(None, description="Filter by payout status"),
    artist_id: Optional[int] = Query(None, description="Filter by artist id"),
    limit: int = Query(50, ge=1, le=500, description="Max rows to return"),
):
    if admin_key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    db = SessionLocal()
    try:
        groups = fetch_admin_ledger_groups(
            db,
            status=status,
            artist_id=artist_id,
            artist_ids_from_name=None,
            limit=limit,
        )
    finally:
        db.close()

    out = []
    for g in groups:
        created = g.created_at or g.period_end_at
        out.append(
            {
                "id": synthetic_ledger_group_id(g.batch_id, g.artist_id),
                "batch_id": g.batch_id,
                "user_id": None,
                "artist_id": g.artist_id,
                "amount": round(float(g.amount_cents) / 100.0, 2),
                "status": g.ui_status,
                "created_at": created.isoformat() if created is not None else None,
                "attempt_count": g.attempt_count,
                "failure_reason": g.failure_reason,
                "algorand_tx_id": g.algorand_tx_id,
                "destination_wallet": g.destination_wallet,
            }
        )
    return out


@router.post("/admin/settle-batch/{batch_id}")
def post_admin_settle_batch(
    batch_id: int,
    admin_key: str = Query(..., description="MVP shared secret; compare to ADMIN_KEY"),
    _reject_impersonation: None = Depends(require_non_impersonation),
):
    """Run V2 on-chain settlement for all artists in a finalized/posted batch."""
    if admin_key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")
    try:
        return process_batch_settlement(batch_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/retry-payout/{payout_id}")
def post_admin_retry_payout(
    payout_id: int,
    admin_key: str = Query(..., description="MVP shared secret; compare to ADMIN_KEY"),
    status: Optional[str] = Query(None),
    artist_id: Optional[str] = Query(None),
    artist_name: Optional[str] = Query(None),
    limit: Optional[int] = Query(None, ge=1, le=500),
    _reject_impersonation: None = Depends(require_non_impersonation),
):
    if admin_key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    raise HTTPException(
        status_code=501,
        detail=(
            "Legacy per-row payout retry is not available for the V2 ledger "
            "(payout_lines / payout_batches). Use batch posting workflows instead."
        ),
    )


@router.get("/admin/payouts-ui", response_class=HTMLResponse)
def admin_payouts_ui(
    admin_key: str = Query(..., description="MVP shared secret; compare to ADMIN_KEY"),
    status: Optional[str] = Query(None, description="Filter by payout status"),
    artist_id: Optional[str] = Query(None, description="Filter by artist id"),
    artist_name: Optional[str] = Query(None, description="Filter by artist name"),
    limit: int = Query(50, ge=1, le=500, description="Max rows in table"),
    msg: Optional[str] = Query(None),
):
    if admin_key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    artist_id_int = None
    if artist_id:
        try:
            artist_id_int = int(artist_id)
        except ValueError:
            artist_id_int = None

    db = SessionLocal()
    try:
        (
            total_count,
            pending_count,
            processing_count,
            accrued_count,
            paid_count,
            failed_count,
        ) = admin_ledger_group_counts(db)

        name_artist_ids = None
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
            payouts = []
        else:
            payouts = fetch_admin_ledger_groups(
                db,
                status=status,
                artist_id=artist_id_int,
                artist_ids_from_name=name_artist_ids,
                limit=limit,
            )
    finally:
        db.close()

    rows_html = ""
    for g in payouts:
        pid = str(g.batch_id)
        uid = str(g.distinct_users) if g.distinct_users else "—"
        if g.artist_name:
            aid = f"{_html_escape(g.artist_name)} (ID: {g.artist_id})"
        else:
            aid = str(g.artist_id)
        amt = round(float(g.amount_cents) / 100.0, 2)
        ui_st = g.ui_status
        low_status = ui_st.lower()
        if low_status in ("paid", "pending", "failed", "processing", "accrued"):
            st = (
                f'<span class="badge badge-{low_status}">'
                f"{_html_escape(low_status.upper())}</span>"
            )
        else:
            st = _html_escape(ui_st)
        ac = g.attempt_count or "0"
        fr = g.failure_reason or "—"
        if g.destination_wallet and str(g.destination_wallet).strip():
            full_wallet = str(g.destination_wallet).strip()
            if len(full_wallet) > 12:
                short_wallet = full_wallet[:6] + "..." + full_wallet[-4:]
            else:
                short_wallet = full_wallet
            js_wallet = json.dumps(full_wallet)
            short_esc = _html_escape(short_wallet)
            dw = (
                f'<span onclick=\'copyText({js_wallet})\' '
                f'style="cursor:pointer;" title="Click to copy">'
                f"{short_esc}</span>"
            )
        else:
            dw = "—"
        if g.algorand_tx_id and str(g.algorand_tx_id).strip():
            raw_tx = str(g.algorand_tx_id).strip()
            short_tx = (
                f"{raw_tx[:4]}...{raw_tx[-4:]}" if len(raw_tx) > 12 else raw_tx
            )
            tx_href = _html_escape(raw_tx)
            tx_label = _html_escape(short_tx)
            tx = (
                f'<a href="{EXPLORER_BASE_URL}/transaction/{tx_href}" '
                f'target="_blank">{tx_label}</a>'
            )
        else:
            tx = "—"
        created_dt = g.created_at or g.period_end_at
        if created_dt is not None:
            created = _html_escape(created_dt.isoformat())
        else:
            created = "—"
        tr_attrs = ""
        retry_cell = "—"
        rows_html += f"""
            <tr{tr_attrs}>
                <td style="padding:10px; border-bottom:1px solid #eee; width:60px;">{pid}</td>
                <td style="padding:10px; border-bottom:1px solid #eee; width:60px;">{uid}</td>
                <td style="padding:10px; border-bottom:1px solid #eee; width:240px;">{aid}</td>
                <td style="padding:10px; border-bottom:1px solid #eee; width:80px;">{amt}</td>
                <td style="padding:10px; border-bottom:1px solid #eee; width:100px;">{st}</td>
                <td class="truncate" style="padding:10px; border-bottom:1px solid #eee; max-width:160px;">{dw}</td>
                <td class="truncate" style="padding:10px; border-bottom:1px solid #eee; max-width:160px;">{tx}</td>
                <td style="padding:10px; border-bottom:1px solid #eee; width:180px;">{created}</td>
                <td style="padding:10px; border-bottom:1px solid #eee; width:80px;">{ac}</td>
                <td class="truncate" style="padding:10px; border-bottom:1px solid #eee; max-width:140px;">{fr}</td>
                <td style="padding:10px; border-bottom:1px solid #eee; width:100px;">{retry_cell}</td>
            </tr>
        """

    if not payouts:
        rows_html = """
            <tr>
                <td colspan="11" style="padding:16px; color:#666;">No payouts match the current filters.</td>
            </tr>
        """

    ak_esc = _html_escape(admin_key)
    artist_val = artist_id or ""
    artist_name_val = artist_name or ""
    sel_all = "selected" if not status else ""
    sel_pending = "selected" if status == "pending" else ""
    sel_processing = "selected" if status == "processing" else ""
    sel_paid = "selected" if status == "paid" else ""
    sel_accrued = "selected" if status == "accrued" else ""
    sel_failed = "selected" if status == "failed" else ""

    # Flash-style messages: URL-only (no session); omit msg from links → no banner.
    messages = {
        "retry_ok": ("Retry triggered successfully", "#e6f9ec", "#1e7e34", "#28a745"),
        "payout_sent": ("Payout sent successfully", "#e6f0ff", "#0d6efd", "#0d6efd"),
        "error_wallet": ("Missing or invalid destination wallet", "#fdecea", "#842029", "#dc3545"),
        "batch_started": ("Batch processing started", "#fff3cd", "#664d03", "#ffc107"),
    }
    msg_block = ""
    if msg and msg in messages:
        text, bg, tc, bc = messages[msg]
        text_esc = _html_escape(text)
        msg_block = f"""
        <div style="
            margin-bottom:20px;
            padding:12px;
            border:1px solid {bc};
            background:{bg};
            color:{tc};
            border-radius:8px;
        ">
            {text_esc}
        </div>
        """
    elif msg is not None:
        logger.warning(f"Unknown msg param: {msg}")

    html = f"""
    <html>
    <head>
    <style>
    .truncate {{
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }}
    .badge {{
        padding: 4px 8px;
        border-radius: 8px;
        font-size: 0.8rem;
        font-weight: 600;
        display: inline-block;
    }}
    .badge-paid {{
        background: #d4edda;
        color: #155724;
    }}
    .badge-pending {{
        background: #fff3cd;
        color: #856404;
    }}
    .badge-failed {{
        background: #f8d7da;
        color: #721c24;
    }}
    .badge-processing {{
        background: #d1ecf1;
        color: #0c5460;
    }}
    .badge-accrued {{
        background: #e7e3fc;
        color: #3d2f7a;
    }}
    </style>
    </head>
    <body style="font-family: Arial; padding: 40px; max-width: 1200px;">
        <h1 style="margin-top:0;">Admin — Payouts</h1>
{msg_block}
        <section style="margin-bottom:24px; padding:20px; border:1px solid #6c757d44; border-radius:12px;">
            <h2 style="margin-top:0;">Summary (all payouts)</h2>
            <p style="margin:0 0 12px 0; color:#555; font-size:0.95rem;">
                Counts are V2 ledger groups (one row per payout batch + artist), summed from
                <code>payout_lines</code>. The table respects filters and limit.
            </p>
            <p style="margin:0; line-height:1.8;">
                <b>Total</b> {total_count}
                &nbsp;|&nbsp; <b>Pending</b> {pending_count}
                &nbsp;|&nbsp; <b>Processing</b> {processing_count}
                &nbsp;|&nbsp; <b>Accrued</b> {accrued_count}
                &nbsp;|&nbsp; <b>Paid (on-chain)</b> {paid_count}
                &nbsp;|&nbsp; <b>Failed</b> {failed_count}
            </p>
        </section>

        <section style="margin-bottom:24px; padding:20px; border:1px solid #ffc10755; border-radius:12px; background:#fffdf5;">
            <h2 style="margin-top:0;">Filters</h2>
            <form method="get" action="/admin/payouts-ui" style="display:flex; flex-wrap:wrap; gap:12px; align-items:flex-end;">
                <input type="hidden" name="admin_key" value="{ak_esc}" />
                <p style="margin:0;">
                    <label for="f_status"><b>Status</b></label><br/>
                    <select name="status" id="f_status" style="margin-top:6px; min-width:160px;">
                        <option value="" {sel_all}>All</option>
                        <option value="pending" {sel_pending}>pending</option>
                        <option value="processing" {sel_processing}>processing</option>
                        <option value="accrued" {sel_accrued}>accrued</option>
                        <option value="paid" {sel_paid}>paid (on-chain)</option>
                        <option value="failed" {sel_failed}>failed</option>
                    </select>
                </p>
                <p style="margin:0;">
                    <label for="f_artist"><b>Artist ID</b></label><br/>
                    <input type="number" name="artist_id" id="f_artist" value="{_html_escape(artist_val)}" min="1" step="1" style="margin-top:6px; width:120px;" />
                </p>
                <p style="margin:0;">
                    <label for="f_artist_name"><b>Artist name</b></label><br/>
                    <input type="text" name="artist_name" id="f_artist_name" value="{_html_escape(artist_name_val)}" placeholder="Artist name" style="margin-top:6px; min-width:180px;" />
                </p>
                <p style="margin:0;">
                    <label for="f_limit"><b>Limit</b></label><br/>
                    <input type="number" name="limit" id="f_limit" value="{limit}" min="1" max="500" step="1" style="margin-top:6px; width:100px;" />
                </p>
                <p style="margin:0;">
                    <button type="submit">Apply filters</button>
                </p>
            </form>
        </section>

        <section style="margin-bottom:32px; padding:20px; border:1px solid #0d6efd33; border-radius:12px; background:#f8fbff;">
            <h2 style="margin-top:0;">Payouts</h2>
            <p style="color:#444; margin-bottom:12px;">
                Ordered by batch period end (newest first). Each row aggregates all lines for one
                batch + artist. &quot;User&quot; = distinct paying users in that group. Showing up to {limit} rows.
            </p>
            <div style="overflow-x:auto;">
            <table style="width:100%; table-layout:fixed; border-collapse:collapse; margin-top:8px; font-size:0.9rem;">
                <thead>
                    <tr style="text-align:left; border-bottom:2px solid #ccc;">
                        <th style="padding:10px; width:60px;">Batch</th>
                        <th style="padding:10px; width:60px;">Users</th>
                        <th style="padding:10px; width:240px;">Artist</th>
                        <th style="padding:10px; width:80px;">Amount</th>
                        <th style="padding:10px; width:100px;">Status</th>
                        <th style="padding:10px; width:160px;">Wallet</th>
                        <th style="padding:10px; width:160px;">Tx</th>
                        <th style="padding:10px; width:180px;">Created</th>
                        <th style="padding:10px; width:80px;">Attempts</th>
                        <th style="padding:10px; width:140px;">Failure</th>
                        <th style="padding:10px; width:100px;">Actions</th>
                    </tr>
                </thead>
                <tbody>{rows_html}</tbody>
            </table>
            </div>
        </section>
    <script>
    function copyText(text) {{
        navigator.clipboard.writeText(text);
    }}
    </script>
    </body></html>
    """

    return html


@router.get("/artist-payouts/{artist_id}", response_class=HTMLResponse)
def artist_payouts(artist_id: int):
    db = SessionLocal()
    try:
        artist = _get_public_artist_or_404(db, artist_id)

        paid_cents, accrued_cents, pending_cents = artist_ledger_bucket_cents(
            db, artist_id
        )
        batch_rows = artist_batch_history(db, artist_id)
    finally:
        db.close()

    total_paid = round(float(paid_cents) / 100.0, 2)
    total_accrued = round(float(accrued_cents) / 100.0, 2)
    total_pending = round(float(pending_cents) / 100.0, 2)
    payout_count = len(batch_rows)
    last_payout_date = "—"
    if batch_rows:
        first = batch_rows[0]
        if first.period_end_at is not None:
            last_payout_date = first.period_end_at.date().isoformat()

    if payout_count == 0:
        history_html = '<p class="ah-muted" style="margin:0;">No payouts yet</p>'
    else:
        rows_html = ""
        for row in batch_rows:
            row_date = (
                row.period_end_at.date().isoformat()
                if row.period_end_at is not None
                else "—"
            )
            amt = round(float(row.amount_cents) / 100.0, 2)
            st = _payout_status_display(row.ui_status)
            n_u = row.distinct_users
            uid = f"{n_u} users" if n_u else "—"
            rows_html += f"""
            <tr>
                <td>{row_date}</td>
                <td>{amt} €</td>
                <td>{st}</td>
                <td class="ah-muted" style="font-size:0.85rem;">{uid}</td>
            </tr>
            """
        history_html = f"""
        <table class="ah-table">
            <thead>
                <tr>
                    <th>Date</th>
                    <th>Amount</th>
                    <th>Status</th>
                    <th class="ah-muted">Users</th>
                </tr>
            </thead>
            <tbody>{rows_html}</tbody>
        </table>
        """

    method_banner = _artist_payout_method_banner(artist)
    m_sel = (artist.payout_method or "none").strip().lower()
    if m_sel not in ALLOWED_PAYOUT_METHODS:
        m_sel = "none"
    sel_none = "selected" if m_sel == "none" else ""
    sel_crypto = "selected" if m_sel == "crypto" else ""
    sel_bank = "selected" if m_sel == "bank" else ""
    w_attr = _html_escape(artist.payout_wallet_address or "")
    b_attr = _html_escape(artist.payout_bank_info or "")

    config_section = f"""
        <section class="ah-card ah-card--payout">
            <h2>Payout method (for future use)</h2>
            <div style="margin-bottom:1.25rem;">
                {method_banner}
            </div>
            <h3 style="margin-top:0; font-size:1rem;">Update settings</h3>
            <form method="post" action="/artist/{artist_id}/payout-method?admin_key={ADMIN_KEY}" style="max-width:32rem;">
                <p style="margin-bottom:10px;">
                    <label for="payout_method"><b>Payout method</b></label><br/>
                    <select name="payout_method" id="payout_method" style="margin-top:6px; min-width:200px;">
                        <option value="none" {sel_none}>None</option>
                        <option value="crypto" {sel_crypto}>Crypto (Algorand)</option>
                        <option value="bank" {sel_bank}>Bank transfer</option>
                    </select>
                </p>
                <p style="margin-bottom:10px;">
                    <label for="payout_wallet_address"><b>Wallet address</b> (crypto)</label><br/>
                    <input type="text" name="payout_wallet_address" id="payout_wallet_address" maxlength="{MAX_PAYOUT_TEXT_LEN}" value="{w_attr}" style="width:100%; max-width:30rem; margin-top:6px; box-sizing:border-box;" />
                </p>
                <p style="margin-bottom:10px;">
                    <label for="payout_bank_info"><b>Bank details</b></label><br/>
                    <textarea name="payout_bank_info" id="payout_bank_info" maxlength="{MAX_PAYOUT_TEXT_LEN}" rows="3" style="width:100%; max-width:30rem; margin-top:6px; box-sizing:border-box;">{b_attr}</textarea>
                </p>
                <p class="ah-form-actions">
                    <button type="submit" class="ah-btn">Save payout method</button>
                </p>
            </form>
            <p class="ah-muted" style="margin-top:16px; margin-bottom:0; font-size:0.85rem;">
                Saving does not move funds. This form includes the MVP admin key in the request URL.
            </p>
        </section>
    """

    html = f"""
    {_artist_hub_html_head(f"Artist {artist_id} — Payouts")}
    <body class="artist-hub">
    <div class="artist-hub-inner">
        <h1>Artist {artist_id} — Payouts</h1>
        {_artist_hub_nav(artist_id, "payouts")}

        {config_section}

        <section class="ah-card ah-card--earnings">
            <h2>Summary</h2>
            <p><b>Paid (on-chain):</b> {round(total_paid, 2)} €</p>
            <p><b>Accrued (not yet on-chain):</b> {round(total_accrued, 2)} €</p>
            <p><b>Pending (batch calculating):</b> {round(total_pending, 2)} €</p>
            <p><b>Number of batches:</b> {payout_count}</p>
            <p><b>Last batch date (top row):</b> {last_payout_date}</p>
            <p class="ah-lead" style="margin-top:12px;">
                <b>Paid</b> requires <code>payout_settlements.execution_status = confirmed</code>.
                <b>Accrued</b> is finalized/posted ledger without confirmed settlement.
            </p>
        </section>

        <section class="ah-card ah-card--compare">
            <h2>Payout history</h2>
            <p class="ah-lead" style="margin-bottom:12px;">
                One row per payout batch (amount is this artist&apos;s share in that batch). Read-only.
            </p>
            {history_html}
        </section>
    </div>
    </body></html>
    """

    return html


@router.get("/artist-analytics/{artist_id}", response_class=HTMLResponse)
def artist_analytics(artist_id: int):
    db = SessionLocal()
    try:
        _get_public_artist_or_404(db, artist_id)
    finally:
        db.close()

    html = f"""
    {_artist_hub_html_head(
        f"Artist {artist_id} — Analytics",
        extra_head='<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>',
    )}
    <body class="artist-hub">
    <div class="artist-hub-inner">

        <h1>Artist {artist_id} — Analytics</h1>
        {_artist_hub_nav(artist_id, "analytics")}

        <section class="ah-card">
            <h2>📊 Streams</h2>
            <div class="ah-range-row">
                <label for="streamsRange"><b>Range:</b></label>
                <select id="streamsRange">
                    <option value="last_day">last_day</option>
                    <option value="last_week">last_week</option>
                    <option value="last_30_days" selected>last_30_days</option>
                    <option value="last_3_months">last_3_months</option>
                    <option value="last_6_months">last_6_months</option>
                    <option value="last_12_months">last_12_months</option>
                    <option value="last_2_years">last_2_years</option>
                    <option value="last_5_years">last_5_years</option>
                </select>
            </div>
            <div id="streamsEmpty" class="ah-muted" style="display:none; margin:8px 0 12px 0;">
                Not enough data yet
            </div>
            <div id="streamsLoading" class="ah-muted" style="display:none; margin:8px 0 12px 0;">
                Loading...
            </div>
            <canvas id="streamsChart" class="ah-chart-canvas"></canvas>
        </section>

        <section class="ah-card">
            <h2>🎵 Top Songs (by streams)</h2>
            <div id="topSongsEmpty" class="ah-muted" style="display:none; margin:8px 0 12px 0;">
                Not enough data yet
            </div>
            <ol id="topSongsList" style="padding-left:22px; margin:0;"></ol>
        </section>

        <section class="ah-card">
            <h2>👥 Top Fans</h2>
            <div id="topFansEmpty" class="ah-muted" style="display:none; margin:8px 0 12px 0;">
                Not enough data yet
            </div>
            <ol id="topFansList" style="padding-left:22px; margin:0; list-style-position: outside;"></ol>
        </section>

        <script>
        let streamsChart = null;
        const streamsRange = document.getElementById("streamsRange");
        const streamsEmpty = document.getElementById("streamsEmpty");
        const streamsLoading = document.getElementById("streamsLoading");
        const streamsCanvas = document.getElementById("streamsChart");
        const topSongsEmpty = document.getElementById("topSongsEmpty");
        const topSongsList = document.getElementById("topSongsList");
        const topFansEmpty = document.getElementById("topFansEmpty");
        const topFansList = document.getElementById("topFansList");

        function escapeHtml(s) {{
            if (s === null || s === undefined) return "";
            return String(s)
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;");
        }}

        async function loadStreams(rangeValue) {{
            streamsLoading.style.display = "block";
            streamsEmpty.style.display = "none";
            try {{
                const res = await fetch(`/artist/{artist_id}/streams?range=${{encodeURIComponent(rangeValue)}}`);
                const data = await res.json();
                const labels = Object.keys(data).sort();
                const values = labels.map((k) => data[k]);

                if (labels.length === 0) {{
                    streamsEmpty.style.display = "block";
                }} else {{
                    streamsEmpty.style.display = "none";
                }}

                if (streamsChart) {{
                    streamsChart.destroy();
                }}

                streamsChart = new Chart(streamsCanvas.getContext("2d"), {{
                    type: "line",
                    data: {{
                        labels: labels,
                        datasets: [{{
                            label: "Streams",
                            data: values,
                            fill: false,
                            tension: 0.1,
                            borderColor: "#60a5fa",
                            backgroundColor: "rgba(96, 165, 250, 0.12)",
                            pointBackgroundColor: "#60a5fa",
                            pointBorderColor: "#1e293b"
                        }}]
                    }},
                    options: {{
                        responsive: true,
                        plugins: {{
                            legend: {{
                                labels: {{ color: "#a1a1aa" }}
                            }}
                        }},
                        scales: {{
                            x: {{
                                ticks: {{ color: "#a1a1aa" }},
                                grid: {{ color: "#27272a" }}
                            }},
                            y: {{
                                beginAtZero: true,
                                ticks: {{ color: "#a1a1aa", precision: 0 }},
                                grid: {{ color: "#27272a" }}
                            }}
                        }}
                    }}
                }});
            }} catch (e) {{
                streamsEmpty.style.display = "block";
                streamsEmpty.textContent = "Not enough data yet";
                if (streamsChart) {{
                    streamsChart.destroy();
                    streamsChart = null;
                }}
            }} finally {{
                streamsLoading.style.display = "none";
            }}
        }}

        async function loadTopSongs(rangeValue) {{
            topSongsEmpty.style.display = "none";
            topSongsList.innerHTML = "";
            try {{
                const res = await fetch(`/artist/{artist_id}/top-songs?range=${{encodeURIComponent(rangeValue)}}`);
                const rows = await res.json();
                if (!Array.isArray(rows) || rows.length === 0) {{
                    topSongsEmpty.style.display = "block";
                    return;
                }}

                const totalStreams = rows.reduce((acc, row) => acc + Number(row.streams || 0), 0);
                rows.forEach((row) => {{
                    const streams = Number(row.streams || 0);
                    const pct = totalStreams > 0 ? ((streams / totalStreams) * 100).toFixed(1) : "0.0";
                    const li = document.createElement("li");
                    li.style.marginBottom = "8px";
                    li.textContent = `${{row.title}} — ${{streams}} streams (${{pct}}%)`;
                    topSongsList.appendChild(li);
                }});
            }} catch (e) {{
                topSongsEmpty.style.display = "block";
            }}
        }}

        async function loadTopFans(rangeValue) {{
            topFansEmpty.style.display = "none";
            topFansList.innerHTML = "";
            try {{
                const res = await fetch(`/artist/{artist_id}/top-fans?range=${{encodeURIComponent(rangeValue)}}`);
                const rows = await res.json();
                if (!Array.isArray(rows) || rows.length === 0) {{
                    topFansEmpty.style.display = "block";
                    return;
                }}

                rows.forEach((row) => {{
                    const streams = Number(row.streams || 0);
                    const top = row.top_song || {{}};
                    const songStreams = Number(top.streams || 0);
                    const songTitle = top.title != null && top.title !== "" ? top.title : "—";
                    const li = document.createElement("li");
                    li.className = "ah-fan-item";
                    li.innerHTML =
                        "<strong>" + escapeHtml(row.username) + "</strong><br>" +
                        streams + " streams<br>" +
                        "Favorite: " + escapeHtml(songTitle) + " (" + songStreams + " streams)";
                    topFansList.appendChild(li);
                }});
            }} catch (e) {{
                topFansEmpty.style.display = "block";
            }}
        }}

        streamsRange.addEventListener("change", (e) => {{
            loadStreams(e.target.value);
            loadTopSongs(e.target.value);
            loadTopFans(e.target.value);
        }});
        loadStreams("last_30_days");
        loadTopSongs("last_30_days");
        loadTopFans("last_30_days");
        </script>
    </div>
    </body></html>
    """

    return html