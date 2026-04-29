"""Add discovery_events telemetry table.

Revision ID: 0032_discovery_events_table
Revises: 0031_release_split_version_source_of_truth
Create Date: 2026-04-29
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0032_discovery_events_table"
down_revision: Union[str, Sequence[str], None] = "0031_release_split_version_source_of_truth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "discovery_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("song_id", sa.Integer(), nullable=True),
        sa.Column("artist_id", sa.Integer(), nullable=True),
        sa.Column("section", sa.String(length=32), nullable=True),
        sa.Column("position", sa.Integer(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
    )
    op.create_index("ix_discovery_events_created_at", "discovery_events", ["created_at"], unique=False)
    op.create_index(
        "ix_discovery_events_event_type_created_at",
        "discovery_events",
        ["event_type", "created_at"],
        unique=False,
    )
    op.create_index("ix_discovery_events_request_id", "discovery_events", ["request_id"], unique=False)
    op.create_index(
        "ix_discovery_events_song_id_created_at",
        "discovery_events",
        ["song_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_discovery_events_user_id_created_at",
        "discovery_events",
        ["user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_discovery_events_user_id_created_at", table_name="discovery_events")
    op.drop_index("ix_discovery_events_song_id_created_at", table_name="discovery_events")
    op.drop_index("ix_discovery_events_request_id", table_name="discovery_events")
    op.drop_index("ix_discovery_events_event_type_created_at", table_name="discovery_events")
    op.drop_index("ix_discovery_events_created_at", table_name="discovery_events")
    op.drop_table("discovery_events")
