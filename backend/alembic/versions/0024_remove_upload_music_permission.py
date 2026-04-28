"""remove deprecated upload_music permission

Revision ID: 0024_remove_upload_music_permission
Revises: 0023_add_studio_context_to_users
Create Date: 2026-04-26 14:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = "0024_remove_upload_music_permission"
down_revision: Union[str, Sequence[str], None] = "0023_add_studio_context_to_users"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PERMISSION_NAME = "upload_music"
_ROLE_RESTORE_MAP: dict[str, tuple[str, ...]] = {
    "admin": (_PERMISSION_NAME,),
    "artist": (_PERMISSION_NAME,),
    "label": (_PERMISSION_NAME,),
}


def _table_exists(bind, table_name: str) -> bool:
    return table_name in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "permissions"):
        return

    permission_row = bind.execute(
        sa.text("SELECT id FROM permissions WHERE name = :name"),
        {"name": _PERMISSION_NAME},
    ).fetchone()
    if permission_row is None:
        return

    permission_id = int(permission_row[0])
    if _table_exists(bind, "role_permissions"):
        bind.execute(
            sa.text("DELETE FROM role_permissions WHERE permission_id = :permission_id"),
            {"permission_id": permission_id},
        )
    bind.execute(
        sa.text("DELETE FROM permissions WHERE id = :permission_id"),
        {"permission_id": permission_id},
    )


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "permissions"):
        return

    permission_row = bind.execute(
        sa.text("SELECT id FROM permissions WHERE name = :name"),
        {"name": _PERMISSION_NAME},
    ).fetchone()
    if permission_row is None:
        bind.execute(
            sa.text("INSERT INTO permissions (name) VALUES (:name)"),
            {"name": _PERMISSION_NAME},
        )
        permission_row = bind.execute(
            sa.text("SELECT id FROM permissions WHERE name = :name"),
            {"name": _PERMISSION_NAME},
        ).fetchone()
    if permission_row is None:
        return
    permission_id = int(permission_row[0])

    if not _table_exists(bind, "role_permissions") or not _table_exists(bind, "roles"):
        return

    role_rows = bind.execute(sa.text("SELECT id, name FROM roles")).fetchall()
    role_id_by_name = {str(name): int(role_id) for role_id, name in role_rows}
    existing_pairs = {
        (int(role_id), int(perm_id))
        for role_id, perm_id in bind.execute(
            sa.text("SELECT role_id, permission_id FROM role_permissions")
        ).fetchall()
    }
    for role_name in _ROLE_RESTORE_MAP:
        role_id = role_id_by_name.get(role_name)
        if role_id is None:
            continue
        pair = (int(role_id), int(permission_id))
        if pair in existing_pairs:
            continue
        bind.execute(
            sa.text(
                "INSERT INTO role_permissions (role_id, permission_id) "
                "VALUES (:role_id, :permission_id)"
            ),
            {"role_id": int(role_id), "permission_id": int(permission_id)},
        )
