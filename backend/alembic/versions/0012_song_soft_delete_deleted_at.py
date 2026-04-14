"""Add soft-delete deleted_at column to songs.

Revision ID: 0012_song_soft_delete_deleted_at
Revises: 0011_song_credit_sound_designer
Create Date: 2026-04-14
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0012_song_soft_delete_deleted_at"
down_revision: Union[str, Sequence[str], None] = "0011_song_credit_sound_designer"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add nullable deleted_at if missing.

    Revision ``0001_bootstrap`` uses ``Base.metadata.create_all()`` against the
    current ORM, so a **fresh** SQLite chain already has ``deleted_at``. Older
    databases upgraded through ``0002``…``0011`` only need the column added here.
    """
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing = {c["name"] for c in insp.get_columns("songs")}
    if "deleted_at" in existing:
        return
    op.add_column(
        "songs",
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing = {c["name"] for c in insp.get_columns("songs")}
    if "deleted_at" not in existing:
        return
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("songs") as batch_op:
            batch_op.drop_column("deleted_at")
    else:
        op.drop_column("songs", "deleted_at")
