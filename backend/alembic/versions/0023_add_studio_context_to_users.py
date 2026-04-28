"""add studio context fields to users

Revision ID: 0023_add_studio_context_to_users
Revises: 0022_drop_legacy_artist_user_id
Create Date: 2026-04-26 13:55:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from app.core.sqlite_migration_utils import safe_sqlite_batch_op


revision = "0023_add_studio_context_to_users"
down_revision = "0022_drop_legacy_artist_user_id"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _column_names(bind, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    return {col["name"] for col in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "users"):
        return
    existing = _column_names(bind, "users")
    def _alter(batch_op) -> None:
        if "current_context_type" not in existing:
            batch_op.add_column(sa.Column("current_context_type", sa.String(length=16), nullable=True))
        if "current_context_id" not in existing:
            batch_op.add_column(sa.Column("current_context_id", sa.Integer(), nullable=True))
    safe_sqlite_batch_op(op, "users", _alter)


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "users"):
        return
    existing = _column_names(bind, "users")
    def _revert(batch_op) -> None:
        if "current_context_id" in existing:
            batch_op.drop_column("current_context_id")
        if "current_context_type" in existing:
            batch_op.drop_column("current_context_type")
    safe_sqlite_batch_op(op, "users", _revert)
