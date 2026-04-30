"""Extend payout_batches.status for processing lock and outcomes.

Revision ID: 0036_payout_batch_status_lock
Revises: 0035_admin_action_logs
Create Date: 2026-04-30
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.core.sqlite_migration_utils import safe_sqlite_batch_op

revision: str = "0036_payout_batch_status_lock"
down_revision: Union[str, Sequence[str], None] = "0035_admin_action_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CK_NAME = "ck_payout_batches_status"
_OLD_SQL = "status IN ('draft', 'calculating', 'finalized', 'posted')"
_NEW_SQL = (
    "status IN ('draft', 'calculating', 'finalized', 'posted', "
    "'processing', 'failed', 'paid')"
)


def _table_exists(bind, table_name: str) -> bool:
    return table_name in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "payout_batches"):
        return

    def _alter(batch_op) -> None:
        batch_op.drop_constraint(_CK_NAME, type_="check")
        batch_op.create_check_constraint(_CK_NAME, _NEW_SQL)

    safe_sqlite_batch_op(op, "payout_batches", _alter)

    if _table_exists(bind, "payout_settlements"):
        op.execute(
            sa.text(
                """
                UPDATE payout_batches
                SET status = 'failed'
                WHERE status IN ('posted', 'finalized')
                  AND EXISTS (
                    SELECT 1
                    FROM payout_settlements ps
                    WHERE ps.batch_id = payout_batches.id
                      AND ps.execution_status = 'failed'
                  )
                """
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "payout_batches"):
        return

    def _revert(batch_op) -> None:
        batch_op.drop_constraint(_CK_NAME, type_="check")
        batch_op.create_check_constraint(_CK_NAME, _OLD_SQL)

    safe_sqlite_batch_op(op, "payout_batches", _revert)
