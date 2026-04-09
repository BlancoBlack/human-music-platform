"""SQLite-only, idempotent schema adjustments shared by app startup and seeding."""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


def _pragma_column_exists(conn, table_name: str, column_name: str) -> bool:
    rows = conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return any(row[1] == column_name for row in rows)


def _sqlite_table_exists(conn, table_name: str) -> bool:
    row = conn.execute(
        text("SELECT 1 FROM sqlite_master WHERE type='table' AND name = :n LIMIT 1"),
        {"n": table_name},
    ).fetchone()
    return row is not None


def ensure_song_credit_entries_position_column(engine: Engine) -> None:
    """
    Rename legacy sort_order → position on song_credit_entries (no data loss).
    """
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as conn:
        if not _sqlite_table_exists(conn, "song_credit_entries"):
            return
        if _pragma_column_exists(conn, "song_credit_entries", "position"):
            return
        if not _pragma_column_exists(conn, "song_credit_entries", "sort_order"):
            return
        logger.info("Renaming column: song_credit_entries.sort_order -> position")
        conn.execute(
            text("ALTER TABLE song_credit_entries RENAME COLUMN sort_order TO position")
        )
