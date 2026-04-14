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


def ensure_song_deleted_at_column(engine: Engine) -> None:
    """Add nullable ``songs.deleted_at`` for soft delete compatibility."""
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as conn:
        if not _sqlite_table_exists(conn, "songs"):
            return
        if _pragma_column_exists(conn, "songs", "deleted_at"):
            return
        logger.info("Applying missing column: songs.deleted_at")
        conn.execute(text("ALTER TABLE songs ADD COLUMN deleted_at DATETIME"))


def ensure_auth_user_schema(engine: Engine) -> None:
    """
    Idempotent SQLite migrations for auth-related tables and columns.

    - Extends legacy ``users`` (id, username) with email, password_hash, is_active,
      is_email_verified, created_at.
    - Creates ``user_profiles`` and ``user_roles``.
    - Adds nullable ``artists.user_id`` for linking Artist → User.

    Non-SQLite engines: no-op (rely on create_all / external migrations).
    """
    if engine.dialect.name != "sqlite":
        return

    with engine.begin() as conn:
        if _sqlite_table_exists(conn, "users"):
            if not _pragma_column_exists(conn, "users", "email"):
                logger.info("Applying missing column: users.email")
                conn.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR(255)"))
            if not _pragma_column_exists(conn, "users", "password_hash"):
                logger.info("Applying missing column: users.password_hash")
                conn.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255)"))
            if not _pragma_column_exists(conn, "users", "is_active"):
                logger.info("Applying missing column: users.is_active")
                conn.execute(
                    text("ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
                )
            if not _pragma_column_exists(conn, "users", "is_email_verified"):
                logger.info("Applying missing column: users.is_email_verified")
                conn.execute(
                    text(
                        "ALTER TABLE users ADD COLUMN is_email_verified INTEGER NOT NULL DEFAULT 0"
                    )
                )
            if not _pragma_column_exists(conn, "users", "created_at"):
                logger.info("Applying missing column: users.created_at")
                conn.execute(text("ALTER TABLE users ADD COLUMN created_at DATETIME"))

            conn.execute(
                text(
                    """
                    UPDATE users
                    SET email = username || '@users.legacy.local'
                    WHERE email IS NULL AND username IS NOT NULL
                    """
                )
            )
            conn.execute(
                text(
                    """
                    UPDATE users
                    SET email = 'user-' || CAST(id AS TEXT) || '@users.legacy.local'
                    WHERE email IS NULL
                    """
                )
            )
            conn.execute(
                text(
                    """
                    UPDATE users SET created_at = datetime('now') WHERE created_at IS NULL
                    """
                )
            )

        if not _sqlite_table_exists(conn, "user_profiles"):
            logger.info("Creating table user_profiles")
            conn.execute(
                text(
                    """
                    CREATE TABLE user_profiles (
                      user_id INTEGER NOT NULL,
                      display_name VARCHAR(255) NOT NULL,
                      avatar_url VARCHAR(512),
                      created_at DATETIME NOT NULL DEFAULT (datetime('now')),
                      PRIMARY KEY (user_id),
                      FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
                    )
                    """
                )
            )

        if not _sqlite_table_exists(conn, "user_roles"):
            logger.info("Creating table user_roles")
            conn.execute(
                text(
                    """
                    CREATE TABLE user_roles (
                      id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                      user_id INTEGER NOT NULL,
                      role VARCHAR(32) NOT NULL,
                      created_at DATETIME NOT NULL DEFAULT (datetime('now')),
                      FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
                      CONSTRAINT uq_user_roles_user_id_role UNIQUE (user_id, role)
                    )
                    """
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_user_roles_user_id "
                    "ON user_roles (user_id)"
                )
            )

        if _sqlite_table_exists(conn, "artists") and not _pragma_column_exists(
            conn, "artists", "user_id"
        ):
            logger.info("Applying missing column: artists.user_id")
            conn.execute(
                text("ALTER TABLE artists ADD COLUMN user_id INTEGER REFERENCES users (id)")
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_artists_user_id ON artists (user_id)"
                )
            )


def ensure_refresh_token_schema(engine: Engine) -> None:
    """Idempotent SQLite: table for refresh JWT revocation (logout)."""
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as conn:
        if _sqlite_table_exists(conn, "refresh_tokens"):
            return
        logger.info("Creating table refresh_tokens")
        conn.execute(
            text(
                """
                CREATE TABLE refresh_tokens (
                  id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                  jti VARCHAR(36) NOT NULL,
                  user_id INTEGER NOT NULL,
                  expires_at DATETIME NOT NULL,
                  revoked_at DATETIME,
                  created_at DATETIME NOT NULL DEFAULT (datetime('now')),
                  FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
                  UNIQUE (jti)
                )
                """
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_refresh_tokens_user_id "
                "ON refresh_tokens (user_id)"
            )
        )
