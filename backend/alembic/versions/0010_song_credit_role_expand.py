"""Expand song_credit_entries.role CHECK to include new credit roles.

Revision ID: 0010_song_credit_role_expand
Revises: 0009_genre_subgenre_slugs
Create Date: 2026-04-13

Role list must stay aligned with app.models.song_credit_entry.CREDIT_ROLE_VALUES
and app.api.routes.SongCreditRole.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from app.core.sqlite_migration_utils import safe_sqlite_batch_op

revision: str = "0010_song_credit_role_expand"
down_revision: Union[str, Sequence[str], None] = "0009_genre_subgenre_slugs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _check_exists(bind, table_name: str, check_name: str) -> bool:
    if not table_exists(bind, table_name):
        return False
    inspector = sa.inspect(bind)
    return any(str(c.get("name")) == check_name for c in inspector.get_check_constraints(table_name))


def _role_check_sql() -> sa.TextClause:
    return sa.text(
        "role IN ("
        "'musician', 'mix engineer', 'mastering engineer', 'producer', 'studio', "
        "'songwriter', 'arranger', 'composer', 'artwork'"
        ")",
    )


def _old_role_check_sql() -> sa.TextClause:
    return sa.text(
        "role IN ("
        "'musician', 'mix engineer', 'mastering engineer', 'producer', 'studio'"
        ")",
    )


def upgrade() -> None:
    bind = op.get_bind()
    if not table_exists(bind, "song_credit_entries"):
        return
    dialect = bind.dialect.name
    role_ck_name = "ck_song_credit_entries_role"

    if dialect == "sqlite":
        had_role_ck = _check_exists(bind, "song_credit_entries", role_ck_name)
        def _alter(batch_op) -> None:
            if had_role_ck:
                batch_op.drop_constraint(role_ck_name, type_="check")
            batch_op.create_check_constraint(
                role_ck_name,
                _role_check_sql(),
            )
        safe_sqlite_batch_op(
            op,
            "song_credit_entries",
            _alter,
            batch_kwargs={"recreate": "always"},
        )
        return

    if _check_exists(bind, "song_credit_entries", role_ck_name):
        op.drop_constraint(role_ck_name, "song_credit_entries", type_="check")
    op.create_check_constraint(
        role_ck_name,
        "song_credit_entries",
        _role_check_sql(),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if not table_exists(bind, "song_credit_entries"):
        return
    dialect = bind.dialect.name
    role_ck_name = "ck_song_credit_entries_role"

    if dialect == "sqlite":
        had_role_ck = _check_exists(bind, "song_credit_entries", role_ck_name)
        def _revert(batch_op) -> None:
            if had_role_ck:
                batch_op.drop_constraint(role_ck_name, type_="check")
            batch_op.create_check_constraint(
                role_ck_name,
                _old_role_check_sql(),
            )
        safe_sqlite_batch_op(
            op,
            "song_credit_entries",
            _revert,
            batch_kwargs={"recreate": "always"},
        )
        return

    if not _check_exists(bind, "song_credit_entries", role_ck_name):
        return
    op.drop_constraint(role_ck_name, "song_credit_entries", type_="check")
    op.create_check_constraint(
        role_ck_name,
        "song_credit_entries",
        _old_role_check_sql(),
    )
