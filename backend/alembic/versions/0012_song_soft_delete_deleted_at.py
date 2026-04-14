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


def _drop_stale_sqlite_batch_table() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return
    inspector = sa.inspect(bind)
    if "_alembic_tmp_songs" not in inspector.get_table_names():
        return
    tmp = sa.Table("_alembic_tmp_songs", sa.MetaData())
    tmp.drop(bind, checkfirst=True)


def _set_sqlite_foreign_keys(enabled: bool) -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return
    bind.exec_driver_sql(f"PRAGMA foreign_keys={'ON' if enabled else 'OFF'}")


def upgrade() -> None:
    _drop_stale_sqlite_batch_table()
    _set_sqlite_foreign_keys(False)
    try:
        with op.batch_alter_table("songs", recreate="always") as batch_op:
            batch_op.add_column(sa.Column("deleted_at", sa.DateTime(), nullable=True))
    finally:
        _set_sqlite_foreign_keys(True)


def downgrade() -> None:
    _drop_stale_sqlite_batch_table()
    _set_sqlite_foreign_keys(False)
    try:
        with op.batch_alter_table("songs", recreate="always") as batch_op:
            batch_op.drop_column("deleted_at")
    finally:
        _set_sqlite_foreign_keys(True)
