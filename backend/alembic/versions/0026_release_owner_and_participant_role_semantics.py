"""add releases.owner_user_id and collaborator participant role

Revision ID: 0026_release_owner_and_participant_role_semantics
Revises: 0025_add_release_participants
Create Date: 2026-04-26 15:05:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa
from app.core.sqlite_migration_utils import (
    safe_sqlite_batch_op,
)

revision: str = "0026_release_owner_and_participant_role_semantics"
down_revision: Union[str, Sequence[str], None] = "0025_add_release_participants"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(bind, table_name: str) -> bool:
    return table_name in sa.inspect(bind).get_table_names()


def _column_names(bind, table_name: str) -> set[str]:
    return {col["name"] for col in sa.inspect(bind).get_columns(table_name)}


def _index_names(bind, table_name: str) -> set[str]:
    return {idx["name"] for idx in sa.inspect(bind).get_indexes(table_name)}


def _foreign_key_names(bind, table_name: str) -> set[str]:
    names: set[str] = set()
    for fk in sa.inspect(bind).get_foreign_keys(table_name):
        name = fk.get("name")
        if name:
            names.add(str(name))
    return names


def upgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "releases"):
        existing_cols = _column_names(bind, "releases")
        existing_idx = _index_names(bind, "releases")
        existing_fks = _foreign_key_names(bind, "releases")

        def _alter_releases(batch_op) -> None:
            if "owner_user_id" not in existing_cols:
                batch_op.add_column(sa.Column("owner_user_id", sa.Integer(), nullable=True))
            if "fk_releases_owner_user_id_users" not in existing_fks:
                batch_op.create_foreign_key(
                    "fk_releases_owner_user_id_users",
                    "users",
                    ["owner_user_id"],
                    ["id"],
                )
            if "ix_releases_owner_user_id" not in existing_idx:
                batch_op.create_index("ix_releases_owner_user_id", ["owner_user_id"])
        safe_sqlite_batch_op(op, "releases", _alter_releases)

        # Backfill owner_user_id from first song's primary artist owner.
        bind.execute(
            sa.text(
                """
                UPDATE releases
                SET owner_user_id = (
                    SELECT a.owner_user_id
                    FROM songs s
                    JOIN artists a ON a.id = s.artist_id
                    WHERE s.release_id = releases.id
                      AND a.owner_user_id IS NOT NULL
                    ORDER BY s.id ASC
                    LIMIT 1
                )
                WHERE owner_user_id IS NULL
                """
            )
        )

    if _table_exists(bind, "release_participants"):
        def _alter_participants(batch_op) -> None:
            batch_op.drop_constraint("ck_release_participants_role_values", type_="check")
            batch_op.create_check_constraint(
                "ck_release_participants_role_values",
                "role IN ('primary','collaborator','featured')",
            )
        safe_sqlite_batch_op(op, "release_participants", _alter_participants)


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "release_participants"):
        def _revert_participant_roles(batch_op) -> None:
            batch_op.drop_constraint("ck_release_participants_role_values", type_="check")
            batch_op.create_check_constraint(
                "ck_release_participants_role_values",
                "role IN ('primary','featured')",
            )
        safe_sqlite_batch_op(op, "release_participants", _revert_participant_roles)

    if _table_exists(bind, "releases") and "owner_user_id" in _column_names(bind, "releases"):
        existing_idx = _index_names(bind, "releases")
        existing_fks = _foreign_key_names(bind, "releases")

        def _revert_releases(batch_op) -> None:
            if "ix_releases_owner_user_id" in existing_idx:
                batch_op.drop_index("ix_releases_owner_user_id")
            if "fk_releases_owner_user_id_users" in existing_fks:
                batch_op.drop_constraint("fk_releases_owner_user_id_users", type_="foreignkey")
            batch_op.drop_column("owner_user_id")
        safe_sqlite_batch_op(op, "releases", _revert_releases)
