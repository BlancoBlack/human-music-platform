"""Deduplicate per-release track_number and add unique index.

Revision ID: 0006_release_track_number_unique
Revises: 0005_song_track_number
Create Date: 2026-04-13
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision: str = "0006_release_track_number_unique"
down_revision: Union[str, Sequence[str], None] = "0005_song_track_number"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX_NAME = "uq_songs_release_id_track_number_idx"


def table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def column_exists(bind, table_name: str, column_name: str) -> bool:
    if not table_exists(bind, table_name):
        return False
    inspector = sa.inspect(bind)
    cols = inspector.get_columns(table_name)
    return any(str(c.get("name")) == column_name for c in cols)


def _index_exists(bind, table_name: str, index_name: str) -> bool:
    if not table_exists(bind, table_name):
        return False
    inspector = sa.inspect(bind)
    return any(str(i.get("name")) == index_name for i in inspector.get_indexes(table_name))


def _release_ids_with_duplicate_track_numbers(conn) -> list[int]:
    """release_id values that have duplicate (release_id, track_number), track_number NOT NULL."""
    rows = conn.execute(
        text(
            """
            SELECT DISTINCT s.release_id
            FROM songs s
            INNER JOIN (
                SELECT release_id, track_number
                FROM songs
                WHERE release_id IS NOT NULL
                  AND track_number IS NOT NULL
                GROUP BY release_id, track_number
                HAVING COUNT(*) > 1
            ) d ON d.release_id = s.release_id AND d.track_number = s.track_number
            """
        )
    ).fetchall()
    out: list[int] = []
    for r in rows:
        if r and r[0] is not None:
            out.append(int(r[0]))
    return sorted(set(out))


def _renumber_release_tracks(conn, release_id: int) -> None:
    rows = conn.execute(
        text(
            """
            SELECT id FROM songs
            WHERE release_id = :rid
            ORDER BY id ASC
            """
        ),
        {"rid": int(release_id)},
    ).fetchall()
    for pos, row in enumerate(rows, start=1):
        sid = int(row[0])
        conn.execute(
            text("UPDATE songs SET track_number = :tn WHERE id = :sid"),
            {"tn": int(pos), "sid": sid},
        )


def upgrade() -> None:
    bind = op.get_bind()
    conn = bind

    if not column_exists(bind, "songs", "track_number"):
        return

    for rid in _release_ids_with_duplicate_track_numbers(conn):
        _renumber_release_tracks(conn, rid)

    if _index_exists(bind, "songs", INDEX_NAME):
        return

    conn.execute(
        text(
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS {INDEX_NAME}
            ON songs (release_id, track_number)
            WHERE track_number IS NOT NULL
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    if not table_exists(bind, "songs"):
        return
    if _index_exists(bind, "songs", INDEX_NAME):
        op.drop_index(INDEX_NAME, table_name="songs")
