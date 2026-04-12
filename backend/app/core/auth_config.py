"""JWT and refresh-token settings (env-driven for production)."""

from __future__ import annotations

import os
from datetime import timedelta

JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE = timedelta(minutes=15)
REFRESH_TOKEN_EXPIRE = timedelta(days=int(os.getenv("JWT_REFRESH_DAYS", "30")))
# Short-lived access JWT when a developer impersonates another user (dev only).
IMPERSONATION_ACCESS_EXPIRE = timedelta(minutes=10)


def is_legacy_header_auth_enabled() -> bool:
    """
    When True, listening/stream endpoints accept deprecated ``X-User-Id`` if no
    Bearer JWT is sent. **Default is False** — never enable in production.
    """
    raw = (os.getenv("ENABLE_LEGACY_AUTH", "false") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _normalized_app_env() -> str:
    return (os.getenv("APP_ENV") or os.getenv("ENV") or "").strip().lower()


def is_dev_environment() -> bool:
    """True when ``APP_ENV`` / ``ENV`` is ``development`` or ``dev``."""
    return _normalized_app_env() in ("development", "dev")


def is_dev_impersonation_enabled() -> bool:
    """
    Dev-only user impersonation. Requires explicit ``ENABLE_DEV_IMPERSONATION`` and
    ``APP_ENV`` (or ``ENV``) set to ``development`` or ``dev``. Never enable in production.
    """
    if not is_dev_environment():
        return False
    raw = (os.getenv("ENABLE_DEV_IMPERSONATION", "") or "").strip().lower()
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
