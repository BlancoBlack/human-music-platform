"""Add playlist_reorder_events (ingest-only reorder signals).

Revision ID: 0040_playlist_reorder_events
Revises: 0039_like_events
Create Date: 2026-05-02
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0040_playlist_reorder_events"
down_revision: Union[str, Sequence[str], None] = "0039_like_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "playlist_reorder_events" not in tables:
        op.create_table(
            "playlist_reorder_events",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("playlist_id", sa.Integer(), nullable=False),
            sa.Column("song_id", sa.Integer(), nullable=False),
            sa.Column("old_position", sa.Integer(), nullable=False),
            sa.Column("new_position", sa.Integer(), nullable=False),
            sa.Column("delta_position", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["playlist_id"], ["playlists.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["song_id"], ["songs.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_playlist_reorder_events_user_id",
            "playlist_reorder_events",
            ["user_id"],
        )
        op.create_index(
            "ix_playlist_reorder_events_playlist_id",
            "playlist_reorder_events",
            ["playlist_id"],
        )
        op.create_index(
            "ix_playlist_reorder_events_song_id",
            "playlist_reorder_events",
            ["song_id"],
        )
        op.create_index(
            "ix_playlist_reorder_events_created_at",
            "playlist_reorder_events",
            ["created_at"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "playlist_reorder_events" in tables:
        op.drop_table("playlist_reorder_events")
