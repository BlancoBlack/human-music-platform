"""Add artist ownership column for future resource-level access control.

Revision ID: 0015_artist_owner_user_id
Revises: 0014_user_roles_role_id_nullable_fk
Create Date: 2026-04-24
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from app.core.sqlite_migration_utils import safe_sqlite_batch_op

revision: str = "0015_artist_owner_user_id"
down_revision: Union[str, Sequence[str], None] = "0014_user_roles_role_id_nullable_fk"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FK_NAME = "fk_artists_owner_user_id_users"
INDEX_NAME = "ix_artists_owner_user_id"


def _column_names(bind) -> set[str]:
    insp = sa.inspect(bind)
    return {c["name"] for c in insp.get_columns("artists")}


def _fk_names(bind) -> set[str]:
    insp = sa.inspect(bind)
    return {str(fk.get("name") or "") for fk in insp.get_foreign_keys("artists")}


def _index_names(bind) -> set[str]:
    insp = sa.inspect(bind)
    return {str(idx.get("name") or "") for idx in insp.get_indexes("artists")}


def upgrade() -> None:
    bind = op.get_bind()
    columns = _column_names(bind)
    if "owner_user_id" not in columns:
        op.add_column("artists", sa.Column("owner_user_id", sa.Integer(), nullable=True))

    fk_names = _fk_names(bind)
    if FK_NAME not in fk_names and bind.dialect.name != "sqlite":
        op.create_foreign_key(
            FK_NAME,
            "artists",
            "users",
            ["owner_user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    index_names = _index_names(bind)
    if INDEX_NAME not in index_names:
        op.create_index(INDEX_NAME, "artists", ["owner_user_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    columns = _column_names(bind)
    if "owner_user_id" not in columns:
        return

    index_names = _index_names(bind)
    if INDEX_NAME in index_names:
        op.drop_index(INDEX_NAME, table_name="artists")

    fk_names = _fk_names(bind)
    if FK_NAME in fk_names and bind.dialect.name != "sqlite":
        op.drop_constraint(FK_NAME, "artists", type_="foreignkey")

    if bind.dialect.name == "sqlite":
        def _revert(batch_op) -> None:
            batch_op.drop_column("owner_user_id")
        safe_sqlite_batch_op(op, "artists", _revert)
    else:
        op.drop_column("artists", "owner_user_id")
