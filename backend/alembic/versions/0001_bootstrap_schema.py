"""Bootstrap schema from SQLAlchemy models (SQLite local dev).

Creates all tables defined on ``Base.metadata`` if missing (``checkfirst=True``).
For production, prefer managed migrations / DBA-reviewed DDL.

Revision ID: 0001_bootstrap
Revises:
Create Date: 2026-04-12

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

from app.core.database import Base

revision: str = "0001_bootstrap"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    """Dev-only: drops all ORM-mapped tables. Do not run against data you need."""
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
