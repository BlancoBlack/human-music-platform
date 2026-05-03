import os
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

ENV_DATABASE_URL = (os.getenv("DATABASE_URL") or "").strip()
ENV_APP_BASE_DIR = (os.getenv("APP_BASE_DIR") or "").strip()


def _derive_base_dir_from_file() -> Path:
    candidate = Path(__file__).resolve().parents[3]
    if not (candidate / "backend").is_dir():
        raise RuntimeError(
            "Could not derive project root from file location. "
            f"Expected backend directory under: {candidate}"
        )
    return candidate


def _resolve_base_dir() -> Path:
    if ENV_APP_BASE_DIR:
        base = Path(ENV_APP_BASE_DIR).expanduser().resolve()
    else:
        base = _derive_base_dir_from_file()
    if not (base / "backend").is_dir():
        raise RuntimeError(
            "Invalid APP_BASE_DIR/project root: expected a 'backend' directory at "
            f"{base / 'backend'}"
        )
    return base


def _validate_writable_directory(path: Path) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(f"Failed to create database directory: {path}") from exc
    if not os.access(path, os.W_OK):
        raise RuntimeError(f"Database directory is not writable: {path}")


if ENV_DATABASE_URL:
    DATABASE_URL = ENV_DATABASE_URL
    BASE_DIR: Optional[Path] = None
    DB_PATH: Optional[Path] = None
else:
    BASE_DIR = _resolve_base_dir()
    db_dir = (BASE_DIR / "backend").resolve()
    _validate_writable_directory(db_dir)
    DB_PATH = (db_dir / "dev.db").resolve()
    DATABASE_URL = f"sqlite:///{DB_PATH.as_posix()}"

_ENGINE_CONNECT_ARGS = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=_ENGINE_CONNECT_ARGS,
)


@event.listens_for(engine, "connect")
def _sqlite_enable_foreign_keys(dbapi_connection, connection_record):
    if not DATABASE_URL.startswith("sqlite"):
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

SessionLocal = sessionmaker(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


Base = declarative_base()

# 🔥 IMPORTANTE: importar modelos DESPUÉS de Base
from app.models import (
    user,
    user_profile,
    user_role,
    role,
    permission,
    role_permission,
    refresh_token,
    song,
    song_featured_artist,
    song_credit_entry,
    song_media_asset,
    ingestion_lock,
    listening_event,
    listening_session,
    listening_session_checkpoint,
    listening_aggregate,
    discovery_event,
    user_balance,
    artist,
    artist_slug_history,
    label,
    song_artist_split,
    release,
    release_participant,
    release_slug_history,
    release_media_asset,
    genre,
    subgenre,
    global_listening_aggregate,
    payout_batch,
    payout_line,
    payout_input_snapshot,
    snapshot_user_pool,
    snapshot_listening_input,
    payout_settlement,
    song_slug_history,
    admin_action_log,
    playlist,
    playlist_reorder_event,
)

# Register model-level slug listeners for all insert paths.
from app.services import slug_service  # noqa: F401