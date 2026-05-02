"""Add playlists and playlist_tracks tables.

Revision ID: 0038_playlists_and_playlist_tracks
Revises: 0037_listening_session_source_context
Create Date: 2026-05-02
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0038_playlists_and_playlist_tracks"
down_revision: Union[str, Sequence[str], None] = "0037_listening_session_source_context"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "playlists" not in tables:
        op.create_table(
            "playlists",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("owner_user_id", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(length=512), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("is_public", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_playlists_owner_user_id", "playlists", ["owner_user_id"])
        op.create_index("ix_playlists_deleted_at", "playlists", ["deleted_at"])

    if "playlist_tracks" not in tables:
        op.create_table(
            "playlist_tracks",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("playlist_id", sa.Integer(), nullable=False),
            sa.Column("song_id", sa.Integer(), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["playlist_id"], ["playlists.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["song_id"], ["songs.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "playlist_id",
                "position",
                name="uq_playlist_tracks_playlist_position",
            ),
            sa.UniqueConstraint(
                "playlist_id",
                "song_id",
                name="uq_playlist_tracks_playlist_song",
            ),
        )
        op.create_index("ix_playlist_tracks_playlist_id", "playlist_tracks", ["playlist_id"])
        op.create_index("ix_playlist_tracks_song_id", "playlist_tracks", ["song_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "playlist_tracks" in tables:
        op.drop_table("playlist_tracks")
    if "playlists" in tables:
        op.drop_table("playlists")
