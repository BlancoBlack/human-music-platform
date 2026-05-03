"""Composite index on like_events (song_id, created_at) for discovery like signal queries.

Revision ID: 0042_like_events_song_created_index
Revises: 0041_playlist_reorder_playlist_updated_at
Create Date: 2026-05-02
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0042_like_events_song_created_index"
down_revision: Union[str, Sequence[str], None] = "0041_playlist_reorder_playlist_updated_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEX_NAME = "ix_like_events_song_created"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "like_events" not in inspector.get_table_names():
        return
    existing = {i["name"] for i in inspector.get_indexes("like_events")}
    if _INDEX_NAME in existing:
        return
    op.create_index(_INDEX_NAME, "like_events", ["song_id", "created_at"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "like_events" not in inspector.get_table_names():
        return
    existing = {i["name"] for i in inspector.get_indexes("like_events")}
    if _INDEX_NAME in existing:
        op.drop_index(_INDEX_NAME, table_name="like_events")
