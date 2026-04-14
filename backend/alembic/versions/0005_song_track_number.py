"""Add songs.track_number for album ordering.

Revision ID: 0005_song_track_number
Revises: 0004_release_container
Create Date: 2026-04-13
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005_song_track_number"
down_revision: Union[str, Sequence[str], None] = "0004_release_container"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def column_exists(bind, table_name: str, column_name: str) -> bool:
    if not table_exists(bind, table_name):
        return False
    inspector = sa.inspect(bind)
    cols = inspector.get_columns(table_name)
    return any(str(c.get("name")) == column_name for c in cols)


def upgrade() -> None:
    bind = op.get_bind()
    if not column_exists(bind, "songs", "track_number"):
        op.add_column("songs", sa.Column("track_number", sa.Integer(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if column_exists(bind, "songs", "track_number"):
        op.drop_column("songs", "track_number")
