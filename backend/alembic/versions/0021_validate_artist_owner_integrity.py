"""Validate artist owner integrity before strict owner-only enforcement.

Revision ID: 0021_validate_artist_owner_integrity
Revises: 0020_backfill_artist_owner_user_id
Create Date: 2026-04-26
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0021_validate_artist_owner_integrity"
down_revision: Union[str, Sequence[str], None] = "0020_backfill_artist_owner_user_id"
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
    if "owner_user_id" not in columns:
        raise RuntimeError(
            "artists.owner_user_id column is missing; cannot enforce owner-only model"
        )

    has_legacy_user_id = "user_id" in columns
    if has_legacy_user_id:
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

    null_count = bind.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM artists
            WHERE owner_user_id IS NULL
            """
        )
    ).scalar_one()

    mismatch_count = 0
    if has_legacy_user_id:
        mismatch_count = bind.execute(
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

    if int(null_count or 0) > 0 or int(mismatch_count or 0) > 0:
        select_user_id_expr = "user_id" if has_legacy_user_id else "NULL AS user_id"
        mismatch_predicate = (
            "OR (user_id IS NOT NULL AND owner_user_id IS NOT NULL AND user_id != owner_user_id)"
            if has_legacy_user_id
            else ""
        )
        sample_rows = bind.execute(
            sa.text(
                f"""
                SELECT id, name, {select_user_id_expr}, owner_user_id, is_system
                FROM artists
                WHERE owner_user_id IS NULL
                   {mismatch_predicate}
                ORDER BY id ASC
                LIMIT 20
                """
            )
        ).fetchall()
        print(
            "[alembic][artist-owner-integrity] "
            f"owner_null={int(null_count or 0)} mismatch={int(mismatch_count or 0)}"
        )
        for artist_id, name, user_id, owner_user_id, is_system in sample_rows:
            print(
                "[alembic][artist-owner-integrity] row "
                f"id={artist_id} name={name!r} user_id={user_id} owner_user_id={owner_user_id} is_system={is_system}"
            )
        raise RuntimeError(
            "Artist ownership integrity check failed. "
            "Resolve NULL/mismatched owner_user_id rows before owner-only rollout."
        )


def downgrade() -> None:
    # Validation migration: no reversible state change.
    pass
