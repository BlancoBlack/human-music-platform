"""
Pytest bootstrap: must run before any test imports ``app.main`` / ``TestClient(app)``.

CI and isolated runs use ``Base.metadata.create_all()`` without ``alembic_version``.
Production/dev still require Alembic via ``_assert_schema_is_current()`` unless this
flag is set.
"""

import os

import pytest

from app.models.role import Role

os.environ["SKIP_SCHEMA_CHECK"] = "1"


@pytest.fixture()
def seed_minimal_rbac_roles():
    """Seed required RBAC roles for create_all()-based test databases."""

    def _seed(db_session) -> None:
        existing = {
            str(name)
            for (name,) in db_session.query(Role.name).filter(
                Role.name.in_(("listener", "artist"))
            )
        }
        rows = []
        if "listener" not in existing:
            rows.append(Role(name="listener"))
        if "artist" not in existing:
            rows.append(Role(name="artist"))
        if rows:
            db_session.add_all(rows)
            db_session.flush()

    return _seed
