"""Prepare user_roles.role_id nullable FK for future RBAC normalization.

Revision ID: 0014_user_roles_role_id_nullable_fk
Revises: 0013_rbac_roles_permissions
Create Date: 2026-04-24
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from app.core.sqlite_migration_utils import safe_sqlite_batch_op

revision: str = "0014_user_roles_role_id_nullable_fk"
down_revision: Union[str, Sequence[str], None] = "0013_rbac_roles_permissions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FK_NAME = "fk_user_roles_role_id_roles"
INDEX_NAME = "ix_user_roles_role_id"


def _column_names(bind) -> set[str]:
    insp = sa.inspect(bind)
    return {c["name"] for c in insp.get_columns("user_roles")}


def _fk_names(bind) -> set[str]:
    insp = sa.inspect(bind)
    return {str(fk.get("name") or "") for fk in insp.get_foreign_keys("user_roles")}


def _index_names(bind) -> set[str]:
    insp = sa.inspect(bind)
    return {str(idx.get("name") or "") for idx in insp.get_indexes("user_roles")}


def upgrade() -> None:
    bind = op.get_bind()
    columns = _column_names(bind)
    if "role_id" not in columns:
        op.add_column("user_roles", sa.Column("role_id", sa.Integer(), nullable=True))

    fk_names = _fk_names(bind)
    if FK_NAME not in fk_names:
        if bind.dialect.name == "sqlite":
            def _add_fk(batch_op) -> None:
                batch_op.create_foreign_key(
                    FK_NAME,
                    "roles",
                    ["role_id"],
                    ["id"],
                    ondelete="SET NULL",
                )
            safe_sqlite_batch_op(op, "user_roles", _add_fk)
        else:
            op.create_foreign_key(
                FK_NAME,
                "user_roles",
                "roles",
                ["role_id"],
                ["id"],
                ondelete="SET NULL",
            )

    index_names = _index_names(bind)
    if INDEX_NAME not in index_names:
        op.create_index(INDEX_NAME, "user_roles", ["role_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    columns = _column_names(bind)
    if "role_id" not in columns:
        return

    index_names = _index_names(bind)
    if INDEX_NAME in index_names:
        op.drop_index(INDEX_NAME, table_name="user_roles")

    fk_names = _fk_names(bind)
    if FK_NAME in fk_names:
        if bind.dialect.name == "sqlite":
            def _drop_fk(batch_op) -> None:
                batch_op.drop_constraint(FK_NAME, type_="foreignkey")
            safe_sqlite_batch_op(op, "user_roles", _drop_fk)
        else:
            op.drop_constraint(FK_NAME, "user_roles", type_="foreignkey")

    if bind.dialect.name == "sqlite":
        def _drop_role_id(batch_op) -> None:
            batch_op.drop_column("role_id")
        safe_sqlite_batch_op(op, "user_roles", _drop_role_id)
    else:
        op.drop_column("user_roles", "role_id")
