"""Add song state machine column and backfill from upload_status.

Revision ID: 0003_song_state_machine
Revises: 0002_metadata_foundation
Create Date: 2026-04-13
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_song_state_machine"
down_revision: Union[str, Sequence[str], None] = "0002_metadata_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    cols = inspector.get_columns(table_name)
    return any(str(c.get("name")) == column_name for c in cols)


def _check_exists(bind, table_name: str, check_name: str) -> bool:
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    checks = inspector.get_check_constraints(table_name)
    return any(str(c.get("name")) == check_name for c in checks)


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if not _column_exists(bind, "songs", "state"):
        op.add_column(
            "songs",
            sa.Column(
                "state",
                sa.String(length=32),
                nullable=False,
                server_default="draft",
            ),
        )

    op.execute(
        sa.text(
            """
            UPDATE songs
            SET state = CASE lower(COALESCE(upload_status, ''))
                WHEN 'ready' THEN 'ready_for_release'
                WHEN 'published' THEN 'ready_for_release'
                WHEN 'audio_uploaded' THEN 'media_ready'
                WHEN 'cover_uploaded' THEN 'media_ready'
                WHEN 'uploaded' THEN 'media_ready'
                ELSE 'draft'
            END
            """
        )
    )

    # Keep lightweight compatibility with SQLite ALTER TABLE limitations.
    if dialect != "sqlite" and not _check_exists(bind, "songs", "ck_songs_state_values"):
        op.create_check_constraint(
            "ck_songs_state_values",
            "songs",
            "state IN ('draft', 'media_ready', 'metadata_ready', 'economy_ready', 'ready_for_release')",
        )

    if dialect != "sqlite":
        op.alter_column("songs", "state", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect != "sqlite" and _check_exists(bind, "songs", "ck_songs_state_values"):
        op.drop_constraint("ck_songs_state_values", "songs", type_="check")

    if _column_exists(bind, "songs", "state"):
        op.drop_column("songs", "state")
