"""Add RBAC tables and seed initial role permissions.

Revision ID: 0013_rbac_roles_permissions
Revises: 0012_song_soft_delete_deleted_at
Create Date: 2026-04-24
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0013_rbac_roles_permissions"
down_revision: Union[str, Sequence[str], None] = "0012_song_soft_delete_deleted_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ROLE_NAMES = (
    "admin",
    "user",
    "artist",
    "label",
    "curator",
    "moderator",
    # Legacy default from auth registration flow.
    "listener",
)

PERMISSION_NAMES = (
    "edit_own_artist",
    "edit_any_artist",
    "view_analytics",
    "create_playlist",
    "write_article",
    "manage_artists",
    "admin_full_access",
)

ROLE_PERMISSION_MAP: dict[str, tuple[str, ...]] = {
    "admin": PERMISSION_NAMES,
    "artist": ("edit_own_artist", "view_analytics"),
    "label": ("manage_artists", "view_analytics"),
    "curator": ("create_playlist", "write_article"),
    "user": (),
    "moderator": (),
    "listener": (),
}


def _seed_roles_and_permissions() -> None:
    bind = op.get_bind()

    roles = sa.table("roles", sa.column("name", sa.String))
    permissions = sa.table("permissions", sa.column("name", sa.String))

    existing_roles = {r[0] for r in bind.execute(sa.text("SELECT name FROM roles")).fetchall()}
    for role_name in ROLE_NAMES:
        if role_name not in existing_roles:
            op.bulk_insert(roles, [{"name": role_name}])

    existing_permissions = {
        r[0] for r in bind.execute(sa.text("SELECT name FROM permissions")).fetchall()
    }
    for permission_name in PERMISSION_NAMES:
        if permission_name not in existing_permissions:
            op.bulk_insert(permissions, [{"name": permission_name}])

    role_rows = bind.execute(sa.text("SELECT id, name FROM roles")).fetchall()
    permission_rows = bind.execute(sa.text("SELECT id, name FROM permissions")).fetchall()
    role_id_by_name = {str(name): int(role_id) for role_id, name in role_rows}
    permission_id_by_name = {str(name): int(permission_id) for permission_id, name in permission_rows}

    existing_pairs = {
        (int(role_id), int(permission_id))
        for role_id, permission_id in bind.execute(
            sa.text("SELECT role_id, permission_id FROM role_permissions")
        ).fetchall()
    }

    rows_to_insert: list[dict[str, int]] = []
    for role_name, permission_names in ROLE_PERMISSION_MAP.items():
        role_id = role_id_by_name.get(role_name)
        if role_id is None:
            continue
        for permission_name in permission_names:
            permission_id = permission_id_by_name.get(permission_name)
            if permission_id is None:
                continue
            pair = (int(role_id), int(permission_id))
            if pair in existing_pairs:
                continue
            rows_to_insert.append(
                {
                    "role_id": int(role_id),
                    "permission_id": int(permission_id),
                }
            )
            existing_pairs.add(pair)

    if rows_to_insert:
        role_permissions = sa.table(
            "role_permissions",
            sa.column("role_id", sa.Integer),
            sa.column("permission_id", sa.Integer),
        )
        op.bulk_insert(role_permissions, rows_to_insert)


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    if "roles" not in tables:
        op.create_table(
            "roles",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(length=64), nullable=False),
        )
        op.create_index("ix_roles_name", "roles", ["name"], unique=True)

    if "permissions" not in tables:
        op.create_table(
            "permissions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(length=64), nullable=False),
        )
        op.create_index("ix_permissions_name", "permissions", ["name"], unique=True)

    if "role_permissions" not in tables:
        op.create_table(
            "role_permissions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("role_id", sa.Integer(), nullable=False),
            sa.Column("permission_id", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"], ondelete="CASCADE"),
            sa.UniqueConstraint(
                "role_id",
                "permission_id",
                name="uq_role_permissions_role_id_permission_id",
            ),
        )
        op.create_index("ix_role_permissions_role_id", "role_permissions", ["role_id"])
        op.create_index(
            "ix_role_permissions_permission_id",
            "role_permissions",
            ["permission_id"],
        )

    _seed_roles_and_permissions()


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    if "role_permissions" in tables:
        op.drop_index("ix_role_permissions_permission_id", table_name="role_permissions")
        op.drop_index("ix_role_permissions_role_id", table_name="role_permissions")
        op.drop_table("role_permissions")
    if "permissions" in tables:
        op.drop_index("ix_permissions_name", table_name="permissions")
        op.drop_table("permissions")
    if "roles" in tables:
        op.drop_index("ix_roles_name", table_name="roles")
        op.drop_table("roles")
