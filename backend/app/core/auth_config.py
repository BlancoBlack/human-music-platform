"""JWT and refresh-token settings (env-driven for production)."""

from __future__ import annotations

import os
from datetime import timedelta

JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE = timedelta(minutes=15)
REFRESH_TOKEN_EXPIRE = timedelta(days=int(os.getenv("JWT_REFRESH_DAYS", "30")))


def is_legacy_header_auth_enabled() -> bool:
    """
    When True (default), listening/stream endpoints accept ``X-User-Id`` if no
    Bearer JWT is sent (deprecated). Set ``ENABLE_LEGACY_AUTH=false`` to
    require JWT only.
    """
    raw = (os.getenv("ENABLE_LEGACY_AUTH", "true") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def require_jwt_secret() -> str:
    """Read secret at call time so tests can set JWT_SECRET_KEY before first use."""
    key = (os.getenv("JWT_SECRET_KEY", "") or "").strip()
    if len(key) < 32:
        raise RuntimeError(
            "JWT_SECRET_KEY must be set to a string of at least 32 characters "
            "(set env JWT_SECRET_KEY for auth)."
        )
    return key


def dev_jwt_secret() -> str:
    """Fixed secret for tests only; never use in production."""
    return "test-jwt-secret-key-do-not-use-in-prod!!"  # 40 chars
