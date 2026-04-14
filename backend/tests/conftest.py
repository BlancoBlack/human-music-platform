"""
Pytest bootstrap: must run before any test imports ``app.main`` / ``TestClient(app)``.

CI and isolated runs use ``Base.metadata.create_all()`` without ``alembic_version``.
Production/dev still require Alembic via ``_assert_schema_is_current()`` unless this
flag is set.
"""

import os

os.environ["SKIP_SCHEMA_CHECK"] = "1"
