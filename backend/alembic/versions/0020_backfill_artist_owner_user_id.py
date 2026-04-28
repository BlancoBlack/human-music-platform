"""Backfill artist.owner_user_id from legacy user_id safely.

Revision ID: 0020_backfill_artist_owner_user_id
Revises: 0019_release_type_ep
Create Date: 2026-04-26
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0020_backfill_artist_owner_user_id"
down_revision: Union[str, Sequence[str], None] = "0019_release_type_ep"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(bind, table_name: str) -> bool:
    insp = sa.inspect(bind)
    return table_name in set(insp.get_table_names())


def _column_names(bind, table_name: str) -> set[str]:
    insp = sa.inspect(bind)
    return {str(c["name"]) for c in insp.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "artists"):
        return
    columns = _column_names(bind, "artists")
    if "owner_user_id" not in columns or "user_id" not in columns:
        return

    # Safe backfill only where owner is missing and a legacy owner exists.
    bind.execute(
        sa.text(
            """
            UPDATE artists
            SET owner_user_id = user_id
            WHERE owner_user_id IS NULL
              AND user_id IS NOT NULL
            """
        )
    )

    # Surface ownership conflicts for manual review (no silent override).
    conflict_count = bind.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM artists
            WHERE owner_user_id IS NOT NULL
              AND user_id IS NOT NULL
              AND owner_user_id != user_id
            """
        )
    ).scalar_one()
    if int(conflict_count or 0) > 0:
        sample_rows = bind.execute(
            sa.text(
                """
                SELECT id, user_id, owner_user_id
                FROM artists
                WHERE owner_user_id IS NOT NULL
                  AND user_id IS NOT NULL
                  AND owner_user_id != user_id
                ORDER BY id ASC
                LIMIT 20
                """
            )
        ).fetchall()
        print(
            "[alembic][artist-ownership] "
            f"Found {int(conflict_count)} artists with owner_user_id != user_id. "
            "Leaving rows unchanged; review required."
        )
        for artist_id, user_id, owner_user_id in sample_rows:
            print(
                "[alembic][artist-ownership] conflict "
                f"artist_id={int(artist_id)} user_id={user_id} owner_user_id={owner_user_id}"
            )


def downgrade() -> None:
    # Irreversible data migration: cannot infer which rows were NULL pre-upgrade.
    pass
