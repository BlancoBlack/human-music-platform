"""add release participants table

Revision ID: 0025_add_release_participants
Revises: 0024_remove_upload_music_permission
Create Date: 2026-04-26 14:50:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = "0025_add_release_participants"
down_revision: Union[str, Sequence[str], None] = "0024_remove_upload_music_permission"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(bind, table_name: str) -> bool:
    return table_name in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "release_participants"):
        return

    op.create_table(
        "release_participants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("release_id", sa.Integer(), nullable=False),
        sa.Column("artist_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["artist_id"], ["artists.id"]),
        sa.ForeignKeyConstraint(["release_id"], ["releases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "release_id",
            "artist_id",
            name="uq_release_participants_release_artist",
        ),
        sa.CheckConstraint(
            "role IN ('primary','featured')",
            name="ck_release_participants_role_values",
        ),
        sa.CheckConstraint(
            "status IN ('pending','accepted','rejected')",
            name="ck_release_participants_status_values",
        ),
    )
    op.create_index(
        "ix_release_participants_release_id",
        "release_participants",
        ["release_id"],
    )
    op.create_index(
        "ix_release_participants_artist_id",
        "release_participants",
        ["artist_id"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "release_participants"):
        return
    op.drop_index("ix_release_participants_artist_id", table_name="release_participants")
    op.drop_index("ix_release_participants_release_id", table_name="release_participants")
    op.drop_table("release_participants")
