"""Allow EP release type.

Revision ID: 0019_release_type_ep
Revises: 0018_public_entity_slugs
Create Date: 2026-04-25
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0019_release_type_ep"
down_revision: Union[str, Sequence[str], None] = "0018_public_entity_slugs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _check_exists(bind, table_name: str, check_name: str) -> bool:
    inspector = sa.inspect(bind)
    return any(str(c.get("name")) == check_name for c in inspector.get_check_constraints(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return
    if _check_exists(bind, "releases", "ck_releases_type_values"):
        op.drop_constraint("ck_releases_type_values", "releases", type_="check")
    op.create_check_constraint(
        "ck_releases_type_values",
        "releases",
        "type IN ('single', 'ep', 'album')",
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return
    if _check_exists(bind, "releases", "ck_releases_type_values"):
        op.drop_constraint("ck_releases_type_values", "releases", type_="check")
    op.create_check_constraint(
        "ck_releases_type_values",
        "releases",
        "type IN ('single', 'album')",
    )
