"""add releases.approval_status

Revision ID: 0029_release_approval_status
Revises: 0028_release_participant_rejection_reason
Create Date: 2026-04-26 16:35:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa
from app.core.sqlite_migration_utils import (
    safe_sqlite_batch_op,
)

revision: str = "0029_release_approval_status"
down_revision: Union[str, Sequence[str], None] = "0028_release_participant_rejection_reason"
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
    checks = {
        c.get("name")
        for c in sa.inspect(bind).get_check_constraints("releases")
    }

    def _alter_releases(batch_op) -> None:
        if "approval_status" not in existing:
            batch_op.add_column(
                sa.Column(
                    "approval_status",
                    sa.String(length=32),
                    nullable=False,
                    server_default="draft",
                )
            )
        if "ck_releases_approval_status_values" not in checks:
            batch_op.create_check_constraint(
                "ck_releases_approval_status_values",
                "approval_status IN ('draft','pending_approvals','ready')",
            )
    safe_sqlite_batch_op(op, "releases", _alter_releases)

    bind.execute(
        sa.text(
            "UPDATE releases SET approval_status = 'pending_approvals' "
            "WHERE approval_status IS NULL OR approval_status = 'draft'"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "releases"):
        return
    existing = _column_names(bind, "releases")
    if "approval_status" not in existing:
        return
    checks = {
        c.get("name")
        for c in sa.inspect(bind).get_check_constraints("releases")
    }

    def _revert_releases(batch_op) -> None:
        if "ck_releases_approval_status_values" in checks:
            batch_op.drop_constraint("ck_releases_approval_status_values", type_="check")
        batch_op.drop_column("approval_status")
    safe_sqlite_batch_op(op, "releases", _revert_releases)
