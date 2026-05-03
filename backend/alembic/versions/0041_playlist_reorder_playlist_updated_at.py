"""Add playlist_updated_at to playlist_reorder_events (post-reorder snapshot).

Revision ID: 0041_playlist_reorder_playlist_updated_at
Revises: 0040_playlist_reorder_events
Create Date: 2026-05-02
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

from app.core.sqlite_migration_utils import is_sqlite, safe_sqlite_batch_op

revision: str = "0041_playlist_reorder_playlist_updated_at"
down_revision: Union[str, Sequence[str], None] = "0040_playlist_reorder_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_columns(inspector, table: str) -> set[str]:
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "playlist_reorder_events" not in inspector.get_table_names():
        return
    cols = _table_columns(inspector, "playlist_reorder_events")
    if "playlist_updated_at" in cols:
        return

    op.add_column(
        "playlist_reorder_events",
        sa.Column("playlist_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        text(
            "UPDATE playlist_reorder_events SET playlist_updated_at = created_at "
            "WHERE playlist_updated_at IS NULL"
        )
    )

    if is_sqlite(bind):

        def _enforce_not_null(batch_op) -> None:
            batch_op.alter_column(
                "playlist_updated_at",
                existing_type=sa.DateTime(timezone=True),
                nullable=False,
            )

        safe_sqlite_batch_op(op, "playlist_reorder_events", _enforce_not_null)
    else:
        op.alter_column(
            "playlist_reorder_events",
            "playlist_updated_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
        )

    inspector = sa.inspect(bind)
    indexes = {i["name"] for i in inspector.get_indexes("playlist_reorder_events")}
    ix = "ix_playlist_reorder_events_user_song_created"
    if ix not in indexes:
        op.create_index(
            ix,
            "playlist_reorder_events",
            ["user_id", "song_id", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "playlist_reorder_events" not in inspector.get_table_names():
        return
    cols = _table_columns(inspector, "playlist_reorder_events")
    if "playlist_updated_at" not in cols:
        return
    ix = "ix_playlist_reorder_events_user_song_created"
    indexes = {i["name"] for i in inspector.get_indexes("playlist_reorder_events")}
    if ix in indexes:
        op.drop_index(ix, table_name="playlist_reorder_events")

    if is_sqlite(bind):

        def _drop_col(batch_op) -> None:
            batch_op.drop_column("playlist_updated_at")

        safe_sqlite_batch_op(op, "playlist_reorder_events", _drop_col)
    else:
        op.drop_column("playlist_reorder_events", "playlist_updated_at")
