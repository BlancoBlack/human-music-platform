"""add release_participants.rejection_reason

Revision ID: 0028_release_participant_rejection_reason
Revises: 0027_release_participant_approvals
Create Date: 2026-04-26 15:50:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa
from app.core.sqlite_migration_utils import safe_sqlite_batch_op

revision: str = "0028_release_participant_rejection_reason"
down_revision: Union[str, Sequence[str], None] = "0027_release_participant_approvals"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(bind, table_name: str) -> bool:
    return table_name in sa.inspect(bind).get_table_names()


def _column_names(bind, table_name: str) -> set[str]:
    return {col["name"] for col in sa.inspect(bind).get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "release_participants"):
        return
    existing = _column_names(bind, "release_participants")
    def _alter(batch_op) -> None:
        if "rejection_reason" not in existing:
            batch_op.add_column(sa.Column("rejection_reason", sa.Text(), nullable=True))
    safe_sqlite_batch_op(op, "release_participants", _alter)


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "release_participants"):
        return
    existing = _column_names(bind, "release_participants")
    if "rejection_reason" in existing:
        def _revert(batch_op) -> None:
            batch_op.drop_column("rejection_reason")
        safe_sqlite_batch_op(op, "release_participants", _revert)
