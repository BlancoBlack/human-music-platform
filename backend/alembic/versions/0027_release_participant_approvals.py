"""add release participant approval fields

Revision ID: 0027_release_participant_approvals
Revises: 0026_release_owner_and_participant_role_semantics
Create Date: 2026-04-26 15:35:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa
from app.core.sqlite_migration_utils import safe_sqlite_batch_op

revision: str = "0027_release_participant_approvals"
down_revision: Union[str, Sequence[str], None] = "0026_release_owner_and_participant_role_semantics"
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
    checks = {
        c.get("name")
        for c in sa.inspect(bind).get_check_constraints("release_participants")
    }

    def _alter(batch_op) -> None:
        if "requires_approval" not in existing:
            batch_op.add_column(
                sa.Column("requires_approval", sa.Boolean(), nullable=False, server_default=sa.true())
            )
        if "approval_type" not in existing:
            batch_op.add_column(
                sa.Column("approval_type", sa.String(length=16), nullable=False, server_default="split")
            )
        if "approved_at" not in existing:
            batch_op.add_column(sa.Column("approved_at", sa.DateTime(), nullable=True))

        if "ck_release_participants_status_values" in checks:
            batch_op.drop_constraint("ck_release_participants_status_values", type_="check")
        batch_op.create_check_constraint(
            "ck_release_participants_status_values",
            "status IN ('pending','accepted','rejected')",
        )
        if "ck_release_participants_approval_type_values" not in checks:
            batch_op.create_check_constraint(
                "ck_release_participants_approval_type_values",
                "approval_type IN ('split','feature','none')",
            )
    safe_sqlite_batch_op(op, "release_participants", _alter)

def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "release_participants"):
        return
    existing = _column_names(bind, "release_participants")
    checks = {
        c.get("name")
        for c in sa.inspect(bind).get_check_constraints("release_participants")
    }

    def _revert(batch_op) -> None:
        if "ck_release_participants_approval_type_values" in checks:
            batch_op.drop_constraint("ck_release_participants_approval_type_values", type_="check")
        if "approved_at" in existing:
            batch_op.drop_column("approved_at")
        if "approval_type" in existing:
            batch_op.drop_column("approval_type")
        if "requires_approval" in existing:
            batch_op.drop_column("requires_approval")
    safe_sqlite_batch_op(op, "release_participants", _revert)
