import logging
import os
from pathlib import Path

from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from dotenv import load_dotenv

# Load backend/.env regardless of process cwd (uvicorn/IDE often start from repo root).
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_BACKEND_ROOT / ".env")

from app.core.logging_config import setup_logging

setup_logging()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from sqlalchemy import inspect, text
from sqlalchemy.engine.url import make_url
from app.api.auth_routes import router as auth_router
from app.api.discovery_routes import router as discovery_router
from app.api.routes import router
from app.core.database import Base, DB_PATH, SessionLocal, engine
from app.core.sqlite_compat import (
    ensure_auth_user_schema,
    ensure_refresh_token_schema,
    ensure_song_credit_entries_position_column,
    ensure_song_deleted_at_column,
)
from app.services.payout_service import ensure_treasury_entities, get_treasury_artist, get_treasury_song

logger = logging.getLogger(__name__)


_DEV_CANONICAL_ORIGIN = "http://localhost:3000"


def _cors_allow_origins() -> list[str]:
    """
    Browsers reject ``Access-Control-Allow-Origin: *`` when credentials are used.
    Set ``CORS_ORIGINS`` to a comma-separated list (default ``http://localhost:3000``).

    ``http://localhost:3000`` is always included so cookie + credentialed flows work
    in local dev even if ``CORS_ORIGINS`` is overridden without it.
    """
    raw = (os.getenv("CORS_ORIGINS", _DEV_CANONICAL_ORIGIN) or "")
    parts = [o.strip() for o in raw.split(",") if o.strip()]
    if not parts:
        parts = [_DEV_CANONICAL_ORIGIN]
    if _DEV_CANONICAL_ORIGIN not in parts:
        parts = [_DEV_CANONICAL_ORIGIN, *parts]
    return list(dict.fromkeys(parts))


class DevOriginWarningMiddleware(BaseHTTPMiddleware):
    """Log when the browser sends ``Origin`` with ``127.0.0.1`` (cookie/CORS mismatch vs ``localhost``)."""

    async def dispatch(self, request: Request, call_next):
        origin = (request.headers.get("origin") or "").strip()
        if origin and "127.0.0.1" in origin:
            logger.warning(
                "Request Origin %r uses 127.0.0.1; prefer http://localhost for dev "
                "(Next.js at http://localhost:3000 and NEXT_PUBLIC_API_BASE=http://localhost:8000) "
                "so cookies and CORS match.",
                origin,
            )
        return await call_next(request)


app = FastAPI(
    title="Human Music Platform API",
    description=(
        "Backend API for streaming events, payout previews, and artist analytics.\n\n"
        "Quick start:\n"
        "1) Read onboarding at `/tutorial`\n"
        "2) Use production streaming endpoints under `Streaming`\n"
        "3) Use `Dev Tools` only for local testing\n\n"
        "Authentication:\n"
        "- Preferred: `Authorization: Bearer <access_token>`\n"
        "- Legacy (dev-only if enabled): `X-User-Id` header"
    ),
    openapi_tags=[
        {
            "name": "Streaming",
            "description": "Production listening ingestion and session tracking.",
        },
        {
            "name": "Payouts",
            "description": "User-centric payout previews and settlement/admin payout routes.",
        },
        {
            "name": "Analytics",
            "description": "Artist and distribution analytics endpoints.",
        },
        {
            "name": "Dev Tools",
            "description": "Development-only endpoints; disabled in production.",
        },
        {
            "name": "Onboarding",
            "description": "Beginner walkthrough and usage tutorial pages.",
        },
    ],
)

# CORS: explicit origins when cookies / Authorization are used from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(DevOriginWarningMiddleware)


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    rows = conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return any(row[1] == column_name for row in rows)


def _sqlite_table_exists(conn, table_name: str) -> bool:
    row = conn.execute(
        text("SELECT 1 FROM sqlite_master WHERE type='table' AND name = :n LIMIT 1"),
        {"n": table_name},
    ).fetchone()
    return row is not None


def _sqlite_index_exists(conn, index_name: str) -> bool:
    row = conn.execute(
        text(
            "SELECT 1 FROM sqlite_master WHERE type='index' AND name = :n LIMIT 1"
        ),
        {"n": index_name},
    ).fetchone()
    return row is not None


def _sqlite_trigger_exists(conn, trigger_name: str) -> bool:
    row = conn.execute(
        text(
            "SELECT 1 FROM sqlite_master WHERE type='trigger' AND name = :n LIMIT 1"
        ),
        {"n": trigger_name},
    ).fetchone()
    return row is not None


def _env_truthy(name: str, default: str = "false") -> bool:
    raw = os.getenv(name, default)
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _schema_bootstrap_enabled() -> bool:
    """
    Explicit escape hatch for isolated local bootstrap only.
    Never enabled by default.
    """
    return _env_truthy("ALLOW_SCHEMA_BOOTSTRAP", "false")


def _is_development_env() -> bool:
    env = (os.getenv("APP_ENV") or os.getenv("ENV") or "").strip().lower()
    return env in {"dev", "development"}


def _alembic_config() -> AlembicConfig:
    return AlembicConfig(str(_BACKEND_ROOT / "alembic.ini"))


def _alembic_head_revision() -> str:
    cfg = _alembic_config()
    script = ScriptDirectory.from_config(cfg)
    heads = list(script.get_heads())
    if len(heads) != 1:
        raise RuntimeError(
            f"Expected exactly one Alembic head revision, got: {heads}"
        )
    return str(heads[0])


def _attempt_dev_auto_migration() -> None:
    if not _is_development_env():
        return
    logger.info("development_auto_migration_start", extra={"target": "head"})
    try:
        cfg = _alembic_config()
        # Prevent Alembic env.py from reconfiguring global logging inside app startup.
        cfg.attributes["skip_logging_config"] = True
        alembic_command.upgrade(cfg, "head")
    except Exception as exc:
        logger.exception("development_auto_migration_failed")
        raise RuntimeError(
            "Automatic Alembic migration failed in development environment. "
            "Run: `cd backend && .venv/bin/alembic upgrade head` and retry."
        ) from exc
    logger.info("development_auto_migration_succeeded", extra={"target": "head"})


def _current_alembic_revisions(conn) -> list[str]:
    insp = inspect(conn)
    if not insp.has_table("alembic_version"):
        return []
    rows = conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()
    return [str(r[0]) for r in rows if r and r[0] is not None]


def _assert_schema_is_current() -> None:
    # Tests use in-memory SQLite + create_all() without Alembic; skip revision check only there.
    if os.getenv("SKIP_SCHEMA_CHECK") == "1":
        return
    head = _alembic_head_revision()
    with engine.connect() as conn:
        revisions = _current_alembic_revisions(conn)
    if not revisions:
        raise RuntimeError(
            "Database schema is not initialized by Alembic. "
            "Run: `cd backend && .venv/bin/alembic upgrade head`"
        )
    if len(revisions) != 1 or revisions[0] != head:
        raise RuntimeError(
            "Database schema is outdated. "
            f"Current alembic revision(s): {revisions}; head: {head}. "
            "Run: `cd backend && .venv/bin/alembic upgrade head`"
        )


def _sanitized_database_url(raw_url: str) -> str:
    """
    Mask username/password for safe logging on non-SQLite databases.
    """
    try:
        url = make_url(raw_url)
    except Exception:
        return "<redacted>"
    if url.username is not None:
        url = url.set(username="****")
    if url.password is not None:
        url = url.set(password="****")
    return url.render_as_string(hide_password=False)


def _ensure_listening_session_hybrid_schema() -> None:
    """SQLite: checkpoints table, session song_id/finalized_at, finalize trigger."""
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as conn:
        if not _sqlite_table_exists(conn, "listening_sessions"):
            return
        if not _column_exists(conn, "listening_sessions", "song_id"):
            logger.info("Applying missing column: listening_sessions.song_id")
            conn.execute(
                text(
                    "ALTER TABLE listening_sessions ADD COLUMN song_id INTEGER "
                    "REFERENCES songs (id)"
                )
            )
        if not _column_exists(conn, "listening_sessions", "finalized_at"):
            logger.info("Applying missing column: listening_sessions.finalized_at")
            conn.execute(
                text("ALTER TABLE listening_sessions ADD COLUMN finalized_at DATETIME")
            )
        conn.execute(
            text(
                """
                UPDATE listening_sessions
                SET finalized_at = (
                  SELECT MIN(le.created_at)
                  FROM listening_events le
                  WHERE le.session_id = listening_sessions.id
                )
                WHERE finalized_at IS NULL
                  AND EXISTS (
                    SELECT 1 FROM listening_events le
                    WHERE le.session_id = listening_sessions.id
                  )
                """
            )
        )
        if not _sqlite_table_exists(conn, "listening_session_checkpoints"):
            logger.info("Creating table listening_session_checkpoints")
            conn.execute(
                text(
                    """
                    CREATE TABLE listening_session_checkpoints (
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      session_id INTEGER NOT NULL REFERENCES listening_sessions (id),
                      user_id INTEGER NOT NULL REFERENCES users (id),
                      song_id INTEGER NOT NULL REFERENCES songs (id),
                      sequence INTEGER NOT NULL,
                      position_seconds INTEGER NOT NULL,
                      created_at DATETIME NOT NULL DEFAULT (datetime('now')),
                      UNIQUE (session_id, sequence)
                    )
                    """
                )
            )
        if not _sqlite_index_exists(
            conn, "ix_listening_session_checkpoints_session_id"
        ):
            conn.execute(
                text(
                    "CREATE INDEX ix_listening_session_checkpoints_session_id "
                    "ON listening_session_checkpoints (session_id)"
                )
            )
        if not _sqlite_index_exists(
            conn, "ix_listening_session_checkpoints_user_id_created_at"
        ):
            conn.execute(
                text(
                    "CREATE INDEX ix_listening_session_checkpoints_user_id_created_at "
                    "ON listening_session_checkpoints (user_id, created_at)"
                )
            )
        if not _sqlite_trigger_exists(conn, "tr_listening_events_mark_session_finalized"):
            logger.info("Creating trigger tr_listening_events_mark_session_finalized")
            conn.execute(
                text(
                    """
                    CREATE TRIGGER tr_listening_events_mark_session_finalized
                    AFTER INSERT ON listening_events
                    FOR EACH ROW
                    WHEN NEW.session_id IS NOT NULL
                    BEGIN
                      UPDATE listening_sessions
                      SET finalized_at = COALESCE(finalized_at, NEW.created_at)
                      WHERE id = NEW.session_id;
                    END
                    """
                )
            )


def _ensure_listening_events_idempotency() -> None:
    """SQLite: add idempotency_key column and partial unique index for legacy DBs."""
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as conn:
        if not _sqlite_table_exists(conn, "listening_events"):
            return
        if not _column_exists(conn, "listening_events", "idempotency_key"):
            logger.info("Applying missing column: listening_events.idempotency_key")
            conn.execute(
                text(
                    "ALTER TABLE listening_events ADD COLUMN idempotency_key VARCHAR(128)"
                )
            )
        if not _sqlite_index_exists(conn, "uq_listening_events_user_idempotency"):
            logger.info("Creating index uq_listening_events_user_idempotency")
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_listening_events_user_idempotency "
                    "ON listening_events(user_id, idempotency_key) "
                    "WHERE idempotency_key IS NOT NULL"
                )
            )


def _ensure_listening_events_correlation_id() -> None:
    """SQLite: add correlation_id column and index for legacy DBs."""
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as conn:
        if not _sqlite_table_exists(conn, "listening_events"):
            return
        if not _column_exists(conn, "listening_events", "correlation_id"):
            logger.info("Applying missing column: listening_events.correlation_id")
            conn.execute(
                text(
                    "ALTER TABLE listening_events ADD COLUMN correlation_id VARCHAR(64)"
                )
            )
        if not _sqlite_index_exists(conn, "ix_listening_events_correlation_id"):
            logger.info("Creating index ix_listening_events_correlation_id")
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_listening_events_correlation_id "
                    "ON listening_events (correlation_id)"
                )
            )


def _ensure_payout_settlements_columns() -> None:
    """Idempotent SQLite-only: ADD COLUMN for ORM fields missing on older DBs."""
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as conn:
        if not _sqlite_table_exists(conn, "payout_settlements"):
            return
        if not _column_exists(conn, "payout_settlements", "splits_digest"):
            logger.info("Applying missing column: splits_digest")
            conn.execute(
                text("ALTER TABLE payout_settlements ADD COLUMN splits_digest VARCHAR(64)")
            )
        if not _column_exists(conn, "payout_settlements", "destination_wallet"):
            logger.info("Applying missing column: destination_wallet")
            conn.execute(
                text(
                    "ALTER TABLE payout_settlements ADD COLUMN destination_wallet VARCHAR(255)"
                )
            )


def _ensure_treasury_schema_constraints() -> None:
    with engine.begin() as conn:
        if not _column_exists(conn, "artists", "system_key"):
            conn.execute(text("ALTER TABLE artists ADD COLUMN system_key VARCHAR(64)"))
        if not _column_exists(conn, "songs", "system_key"):
            conn.execute(text("ALTER TABLE songs ADD COLUMN system_key VARCHAR(64)"))

        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_artists_system_key "
                "ON artists(system_key) WHERE system_key IS NOT NULL"
            )
        )
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_songs_system_key "
                "ON songs(system_key) WHERE system_key IS NOT NULL"
            )
        )


@app.on_event("startup")
def startup_init() -> None:
    logger.info(
        "app_environment",
        extra={
            "APP_ENV": os.getenv("APP_ENV"),
            "ENV": os.getenv("ENV"),
            "ENABLE_DEV_ENDPOINTS": os.getenv("ENABLE_DEV_ENDPOINTS"),
            **(
                {"DB_PATH": str(DB_PATH)}
                if str(engine.url).startswith("sqlite")
                else {"DATABASE_URL": _sanitized_database_url(str(engine.url))}
            ),
        },
    )
    if _schema_bootstrap_enabled():
        logger.warning(
            "ALLOW_SCHEMA_BOOTSTRAP is enabled. "
            "Running create_all/compat schema bootstrap. "
            "Use only for isolated local development."
        )
        Base.metadata.create_all(bind=engine)
        ensure_song_credit_entries_position_column(engine)
        ensure_song_deleted_at_column(engine)
        ensure_auth_user_schema(engine)
        ensure_refresh_token_schema(engine)
        _ensure_listening_session_hybrid_schema()
        _ensure_listening_events_idempotency()
        _ensure_listening_events_correlation_id()
        _ensure_payout_settlements_columns()
        _ensure_treasury_schema_constraints()
    else:
        _attempt_dev_auto_migration()
        _assert_schema_is_current()
    db = SessionLocal()
    try:
        ensure_treasury_entities(db)
        treasury_artist = get_treasury_artist(db)
        treasury_song = get_treasury_song(db)
        if treasury_artist is None or treasury_song is None:
            raise RuntimeError("Treasury invariant failed at startup")
    finally:
        db.close()

# rutas
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(discovery_router, prefix="/discovery", tags=["discovery"])
app.include_router(router)

_uploads_dir = Path("uploads")
_uploads_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(_uploads_dir)), name="uploads")