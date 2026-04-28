"""Drop legacy artists.user_id column after owner-only migration.

Revision ID: 0022_drop_legacy_artist_user_id
Revises: 0021_validate_artist_owner_integrity
Create Date: 2026-04-26
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from app.core.sqlite_migration_utils import safe_sqlite_batch_op

revision: str = "0022_drop_legacy_artist_user_id"
down_revision: Union[str, Sequence[str], None] = "0021_validate_artist_owner_integrity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LEGACY_INDEX_NAME = "ix_artists_user_id"
LEGACY_FK_NAME = "fk_artists_user_id_users"


def _table_exists(bind, table_name: str) -> bool:
    insp = sa.inspect(bind)
    return table_name in set(insp.get_table_names())


def _column_names(bind, table_name: str) -> set[str]:
    insp = sa.inspect(bind)
    return {str(c["name"]) for c in insp.get_columns(table_name)}


def _index_names(bind, table_name: str) -> set[str]:
    insp = sa.inspect(bind)
    return {str(idx.get("name") or "") for idx in insp.get_indexes(table_name)}


def _fk_names(bind, table_name: str) -> set[str]:
    insp = sa.inspect(bind)
    return {str(fk.get("name") or "") for fk in insp.get_foreign_keys(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "artists"):
        return

    columns = _column_names(bind, "artists")
    if "user_id" not in columns:
        return

    index_names = _index_names(bind, "artists")
    if LEGACY_INDEX_NAME in index_names:
        op.drop_index(LEGACY_INDEX_NAME, table_name="artists")

    fk_names = _fk_names(bind, "artists")
    if LEGACY_FK_NAME in fk_names and bind.dialect.name != "sqlite":
        op.drop_constraint(LEGACY_FK_NAME, "artists", type_="foreignkey")

    if bind.dialect.name == "sqlite":
        def _alter(batch_op) -> None:
            batch_op.drop_column("user_id")
        safe_sqlite_batch_op(op, "artists", _alter)
    else:
        op.drop_column("artists", "user_id")


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "artists"):
        return
    columns = _column_names(bind, "artists")
    if "user_id" in columns:
        return

    op.add_column("artists", sa.Column("user_id", sa.Integer(), nullable=True))

    if bind.dialect.name != "sqlite":
        op.create_foreign_key(
            LEGACY_FK_NAME,
            "artists",
            "users",
            ["user_id"],
            ["id"],
        )

    index_names = _index_names(bind, "artists")
    if LEGACY_INDEX_NAME not in index_names:
        op.create_index(LEGACY_INDEX_NAME, "artists", ["user_id"], unique=False)
