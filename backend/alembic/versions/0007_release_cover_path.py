"""Add releases.cover_path for release-level artwork.

Revision ID: 0007_release_cover_path
Revises: 0006_release_track_number_unique
Create Date: 2026-04-13
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007_release_cover_path"
down_revision: Union[str, Sequence[str], None] = "0006_release_track_number_unique"
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
    if not table_exists(bind, "releases"):
        return
    if not column_exists(bind, "releases", "cover_path"):
        op.add_column("releases", sa.Column("cover_path", sa.String(length=512), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if column_exists(bind, "releases", "cover_path"):
        op.drop_column("releases", "cover_path")
