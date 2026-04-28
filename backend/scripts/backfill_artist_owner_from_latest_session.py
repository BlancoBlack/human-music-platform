#!/usr/bin/env python3
"""Backfill dev artist ownership to the active auth user."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def _infer_user_id(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        """
        SELECT user_id
        FROM refresh_tokens
        WHERE revoked_at IS NULL
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """
    ).fetchone()
    if row is None or row[0] is None:
        raise SystemExit("No active refresh token found; pass --user-id explicitly.")
    return int(row[0])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Assign non-system artists with NULL owner_user_id to a dev user."
    )
    parser.add_argument(
        "--db",
        default=str(Path(__file__).resolve().parents[1] / "dev.db"),
        help="Path to SQLite database (default: backend/dev.db)",
    )
    parser.add_argument(
        "--user-id",
        type=int,
        default=None,
        help="User id to assign. Defaults to latest active refresh token user.",
    )
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    if not db_path.is_file():
        raise SystemExit(f"Database not found: {db_path}")

    conn = sqlite3.connect(str(db_path))
    try:
        user_id = int(args.user_id) if args.user_id is not None else _infer_user_id(conn)
        before = conn.execute(
            """
            SELECT COUNT(*)
            FROM artists
            WHERE COALESCE(is_system, 0) = 0 AND owner_user_id IS NULL
            """
        ).fetchone()[0]
        conn.execute(
            """
            UPDATE artists
            SET owner_user_id = ?
            WHERE COALESCE(is_system, 0) = 0 AND owner_user_id IS NULL
            """,
            (user_id,),
        )
        conn.commit()
        after = conn.execute(
            """
            SELECT COUNT(*)
            FROM artists
            WHERE COALESCE(is_system, 0) = 0 AND owner_user_id IS NULL
            """
        ).fetchone()[0]
        print(
            f"Assigned {before - after} artist rows to owner_user_id={user_id}. "
            f"Remaining NULL owner artists: {after}."
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
