"""Add discovery section/position context to listening_sessions.

Revision ID: 0034_add_discovery_context_to_listening_sessions
Revises: 0033_listening_session_discovery_request_id
Create Date: 2026-04-29
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0034_add_discovery_context_to_listening_sessions"
down_revision: Union[str, Sequence[str], None] = "0033_listening_session_discovery_request_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("listening_sessions")}
    if "discovery_section" not in columns:
        op.add_column(
            "listening_sessions",
            sa.Column("discovery_section", sa.String(length=32), nullable=True),
        )
    if "discovery_position" not in columns:
        op.add_column(
            "listening_sessions",
            sa.Column("discovery_position", sa.Integer(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("listening_sessions")}
    if "discovery_position" in columns:
        op.drop_column("listening_sessions", "discovery_position")
    if "discovery_section" in columns:
        op.drop_column("listening_sessions", "discovery_section")
