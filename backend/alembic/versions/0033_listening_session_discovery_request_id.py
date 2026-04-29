"""Add discovery_request_id to listening_sessions.

Revision ID: 0033_listening_session_discovery_request_id
Revises: 0032_discovery_events_table
Create Date: 2026-04-29
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0033_listening_session_discovery_request_id"
down_revision: Union[str, Sequence[str], None] = "0032_discovery_events_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "listening_sessions",
        sa.Column("discovery_request_id", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("listening_sessions", "discovery_request_id")
