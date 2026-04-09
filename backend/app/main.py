import logging
import os
from dotenv import load_dotenv

load_dotenv()

from app.core.logging_config import setup_logging

setup_logging()

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from app.api.routes import router
from app.core.database import Base, SessionLocal, engine
from app.core.sqlite_compat import ensure_song_credit_entries_position_column
from app.services.payout_service import ensure_treasury_entities, get_treasury_artist, get_treasury_song

logger = logging.getLogger(__name__)

app = FastAPI()

# 🔥 CORS (CLAVE)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # en producción se restringe
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
        },
    )
    Base.metadata.create_all(bind=engine)
    ensure_song_credit_entries_position_column(engine)
    _ensure_listening_events_idempotency()
    _ensure_listening_events_correlation_id()
    _ensure_payout_settlements_columns()
    _ensure_treasury_schema_constraints()
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
app.include_router(router)

_uploads_dir = Path("uploads")
_uploads_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(_uploads_dir)), name="uploads")