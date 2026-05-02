"""Add like_events table (user song likes).

Revision ID: 0039_like_events
Revises: 0038_playlists_and_playlist_tracks
Create Date: 2026-05-02
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0039_like_events"
down_revision: Union[str, Sequence[str], None] = "0038_playlists_and_playlist_tracks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "like_events" not in tables:
        op.create_table(
            "like_events",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("song_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["song_id"], ["songs.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "song_id", name="uq_like_events_user_song"),
        )
        op.create_index("ix_like_events_user_id", "like_events", ["user_id"])
        op.create_index("ix_like_events_song_id", "like_events", ["song_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "like_events" in tables:
        op.drop_table("like_events")
