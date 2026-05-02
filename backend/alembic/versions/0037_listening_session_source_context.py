"""Add source_type/source_id to listening_sessions for playback attribution.

Revision ID: 0037_listening_session_source_context
Revises: 0036_payout_batch_status_lock
Create Date: 2026-05-02
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0037_listening_session_source_context"
down_revision: Union[str, Sequence[str], None] = "0036_payout_batch_status_lock"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("listening_sessions")}
    if "source_type" not in columns:
        op.add_column(
            "listening_sessions",
            sa.Column("source_type", sa.String(length=32), nullable=True),
        )
    if "source_id" not in columns:
        op.add_column(
            "listening_sessions",
            sa.Column("source_id", sa.String(length=128), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("listening_sessions")}
    if "source_id" in columns:
        op.drop_column("listening_sessions", "source_id")
    if "source_type" in columns:
        op.drop_column("listening_sessions", "source_type")
