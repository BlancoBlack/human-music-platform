"""add split versioning and participant approved split version

Revision ID: 0030_split_versioning_approval_invalidation
Revises: 0029_release_approval_status
Create Date: 2026-04-26 16:50:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = "0030_split_versioning_approval_invalidation"
down_revision: Union[str, Sequence[str], None] = "0029_release_approval_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(bind, table_name: str) -> bool:
    return table_name in sa.inspect(bind).get_table_names()


def _column_names(bind, table_name: str) -> set[str]:
    return {col["name"] for col in sa.inspect(bind).get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, "song_artist_splits"):
        existing = _column_names(bind, "song_artist_splits")
        if "version" not in existing:
            op.add_column(
                "song_artist_splits",
                sa.Column(
                    "version",
                    sa.Integer(),
                    nullable=False,
                    server_default="1",
                ),
            )

    if _table_exists(bind, "release_participants"):
        existing = _column_names(bind, "release_participants")
        if "approved_split_version" not in existing:
            op.add_column(
                "release_participants",
                sa.Column("approved_split_version", sa.Integer(), nullable=True),
            )


def downgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, "release_participants"):
        existing = _column_names(bind, "release_participants")
        if "approved_split_version" in existing:
            op.drop_column("release_participants", "approved_split_version")

    if _table_exists(bind, "song_artist_splits"):
        existing = _column_names(bind, "song_artist_splits")
        if "version" in existing:
            op.drop_column("song_artist_splits", "version")
