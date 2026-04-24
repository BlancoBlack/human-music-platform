"""Add labels table and user onboarding state for role-based registration.

Revision ID: 0016_registration_roles_onboarding_labels
Revises: 0015_artist_owner_user_id
Create Date: 2026-04-24
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0016_registration_roles_onboarding_labels"
down_revision: Union[str, Sequence[str], None] = "0015_artist_owner_user_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(bind, table_name: str) -> set[str]:
    insp = sa.inspect(bind)
    return {c["name"] for c in insp.get_columns(table_name)}


def _index_names(bind, table_name: str) -> set[str]:
    insp = sa.inspect(bind)
    return {str(i.get("name") or "") for i in insp.get_indexes(table_name)}


def _table_names(bind) -> set[str]:
    insp = sa.inspect(bind)
    return set(insp.get_table_names())


def _fk_names(bind, table_name: str) -> set[str]:
    insp = sa.inspect(bind)
    return {str(fk.get("name") or "") for fk in insp.get_foreign_keys(table_name)}


def upgrade() -> None:
    bind = op.get_bind()

    user_cols = _column_names(bind, "users")
    if "onboarding_completed" not in user_cols:
        op.add_column(
            "users",
            sa.Column(
                "onboarding_completed",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
        )
        op.execute(
            sa.text(
                "UPDATE users SET onboarding_completed = 1 WHERE onboarding_completed IS NULL"
            )
        )
        op.alter_column("users", "onboarding_completed", server_default=None)

    tables = _table_names(bind)
    if "labels" not in tables:
        op.create_table(
            "labels",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("owner_user_id", sa.Integer(), nullable=True),
            sa.Column("name", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )

    label_indexes = _index_names(bind, "labels")
    if "ix_labels_owner_user_id" not in label_indexes:
        op.create_index("ix_labels_owner_user_id", "labels", ["owner_user_id"], unique=False)

    fk_name = "fk_labels_owner_user_id_users"
    label_fks = _fk_names(bind, "labels")
    if fk_name not in label_fks and bind.dialect.name != "sqlite":
        op.create_foreign_key(
            fk_name,
            "labels",
            "users",
            ["owner_user_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    bind = op.get_bind()
    tables = _table_names(bind)

    if "labels" in tables:
        idx = _index_names(bind, "labels")
        if "ix_labels_owner_user_id" in idx:
            op.drop_index("ix_labels_owner_user_id", table_name="labels")
        fks = _fk_names(bind, "labels")
        fk_name = "fk_labels_owner_user_id_users"
        if fk_name in fks and bind.dialect.name != "sqlite":
            op.drop_constraint(fk_name, "labels", type_="foreignkey")
        op.drop_table("labels")

    user_cols = _column_names(bind, "users")
    if "onboarding_completed" in user_cols:
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("users") as batch_op:
                batch_op.drop_column("onboarding_completed")
        else:
            op.drop_column("users", "onboarding_completed")
