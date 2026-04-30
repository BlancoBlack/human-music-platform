"""Add admin action logs table.

Revision ID: 0035_admin_action_logs
Revises: 0034_add_discovery_context_to_listening_sessions
Create Date: 2026-04-29
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0035_admin_action_logs"
down_revision: Union[str, Sequence[str], None] = (
    "0034_add_discovery_context_to_listening_sessions"
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())
    if "admin_action_logs" not in existing_tables:
        op.create_table(
            "admin_action_logs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("admin_user_id", sa.Integer(), nullable=False),
            sa.Column("action_type", sa.String(length=64), nullable=False),
            sa.Column("target_id", sa.Integer(), nullable=False),
            sa.Column("metadata", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["admin_user_id"], ["users.id"], ondelete="CASCADE"),
        )
    indexes = {str(idx.get("name") or "") for idx in inspector.get_indexes("admin_action_logs")}
    if "ix_admin_action_logs_admin_user_id" not in indexes:
        op.create_index(
            "ix_admin_action_logs_admin_user_id",
            "admin_action_logs",
            ["admin_user_id"],
            unique=False,
        )
    if "ix_admin_action_logs_action_type" not in indexes:
        op.create_index(
            "ix_admin_action_logs_action_type",
            "admin_action_logs",
            ["action_type"],
            unique=False,
        )
    if "ix_admin_action_logs_target_id" not in indexes:
        op.create_index(
            "ix_admin_action_logs_target_id",
            "admin_action_logs",
            ["target_id"],
            unique=False,
        )
    if "ix_admin_action_logs_created_at" not in indexes:
        op.create_index(
            "ix_admin_action_logs_created_at",
            "admin_action_logs",
            ["created_at"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())
    if "admin_action_logs" not in existing_tables:
        return
    indexes = {str(idx.get("name") or "") for idx in inspector.get_indexes("admin_action_logs")}
    if "ix_admin_action_logs_created_at" in indexes:
        op.drop_index("ix_admin_action_logs_created_at", table_name="admin_action_logs")
    if "ix_admin_action_logs_target_id" in indexes:
        op.drop_index("ix_admin_action_logs_target_id", table_name="admin_action_logs")
    if "ix_admin_action_logs_action_type" in indexes:
        op.drop_index("ix_admin_action_logs_action_type", table_name="admin_action_logs")
    if "ix_admin_action_logs_admin_user_id" in indexes:
        op.drop_index("ix_admin_action_logs_admin_user_id", table_name="admin_action_logs")
    op.drop_table("admin_action_logs")
