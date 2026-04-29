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
    op.add_column(
        "listening_sessions",
        sa.Column("discovery_section", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "listening_sessions",
        sa.Column("discovery_position", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("listening_sessions", "discovery_position")
    op.drop_column("listening_sessions", "discovery_section")
