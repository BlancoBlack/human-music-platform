"""add releases.split_version deterministic source of truth

Revision ID: 0031_release_split_version_source_of_truth
Revises: 0030_split_versioning_approval_invalidation
Create Date: 2026-04-26 17:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa
from app.core.sqlite_migration_utils import safe_sqlite_batch_op

revision: str = "0031_release_split_version_source_of_truth"
down_revision: Union[str, Sequence[str], None] = "0030_split_versioning_approval_invalidation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(bind, table_name: str) -> bool:
    return table_name in sa.inspect(bind).get_table_names()


def _column_names(bind, table_name: str) -> set[str]:
    return {col["name"] for col in sa.inspect(bind).get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "releases"):
        return
    existing = _column_names(bind, "releases")
    if "split_version" in existing:
        return

    def _alter(batch_op) -> None:
        batch_op.add_column(
            sa.Column(
                "split_version",
                sa.Integer(),
                nullable=False,
                server_default="1",
            )
        )

    safe_sqlite_batch_op(op, "releases", _alter)
    bind.execute(sa.text("UPDATE releases SET split_version = 1 WHERE split_version IS NULL"))


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "releases"):
        return
    existing = _column_names(bind, "releases")
    if "split_version" not in existing:
        return

    def _revert(batch_op) -> None:
        batch_op.drop_column("split_version")

    safe_sqlite_batch_op(op, "releases", _revert)
