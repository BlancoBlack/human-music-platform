"""JWT access and refresh tokens (PyJWT)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import jwt

from app.core.auth_config import (
    ACCESS_TOKEN_EXPIRE,
    JWT_ALGORITHM,
    REFRESH_TOKEN_EXPIRE,
    require_jwt_secret,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(user_id: int, *, secret: str | None = None) -> str:
    """Short-lived access token: sub, exp, iat (typ=access)."""
    key = secret if secret is not None else require_jwt_secret()
    now = _utcnow()
    exp = now + ACCESS_TOKEN_EXPIRE
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": exp,
        "typ": "access",
    }
    return jwt.encode(payload, key, algorithm=JWT_ALGORITHM)


def create_refresh_token(
    user_id: int,
    jti: str,
    *,
    secret: str | None = None,
) -> tuple[str, datetime]:
    """
    Long-lived refresh token: sub, exp, iat, typ=refresh, jti.
    Returns (token, expires_at).
    """
    key = secret if secret is not None else require_jwt_secret()
    now = _utcnow()
    exp = now + REFRESH_TOKEN_EXPIRE
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": exp,
        "typ": "refresh",
        "jti": jti,
    }
    token = jwt.encode(payload, key, algorithm=JWT_ALGORITHM)
    if exp.tzinfo is not None:
        exp = exp.replace(tzinfo=None)
    return token, exp


def decode_access_token(token: str, *, secret: str | None = None) -> dict:
    key = secret if secret is not None else require_jwt_secret()
    data = jwt.decode(
        token,
        key,
        algorithms=[JWT_ALGORITHM],
        options={"require": ["exp", "iat", "sub"]},
    )
    if data.get("typ") != "access":
        raise jwt.InvalidTokenError("not an access token")
    return data


def decode_refresh_token(token: str, *, secret: str | None = None) -> dict:
    key = secret if secret is not None else require_jwt_secret()
    data = jwt.decode(
        token,
        key,
        algorithms=[JWT_ALGORITHM],
        options={"require": ["exp", "iat", "sub"]},
    )
    if data.get("typ") != "refresh":
        raise jwt.InvalidTokenError("not a refresh token")
    jti = data.get("jti")
    if not jti or not isinstance(jti, str):
        raise jwt.InvalidTokenError("missing jti")
    return data


def new_refresh_jti() -> str:
    return str(uuid.uuid4())
