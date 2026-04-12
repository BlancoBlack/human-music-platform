"""JWT access and refresh tokens (PyJWT)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import jwt

from app.core.auth_config import (
    ACCESS_TOKEN_EXPIRE,
    IMPERSONATION_ACCESS_EXPIRE,
    JWT_ALGORITHM,
    REFRESH_TOKEN_EXPIRE,
    require_jwt_secret,
)

ACCESS_TYP = "access"
ACCESS_IMPERSONATION_TYP = "access_impersonation"


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
        "typ": ACCESS_TYP,
    }
    return jwt.encode(payload, key, algorithm=JWT_ALGORITHM)


def create_impersonation_access_token(
    target_user_id: int,
    actor_id: int,
    *,
    secret: str | None = None,
) -> str:
    """Dev-only: access JWT for ``target_user_id`` with ``actor`` who minted it."""
    key = secret if secret is not None else require_jwt_secret()
    now = _utcnow()
    exp = now + IMPERSONATION_ACCESS_EXPIRE
    payload = {
        "sub": str(int(target_user_id)),
        "actor": int(actor_id),
        "iat": now,
        "exp": exp,
        "typ": ACCESS_IMPERSONATION_TYP,
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
    typ = data.get("typ")
    if typ == ACCESS_TYP:
        return data
    if typ == ACCESS_IMPERSONATION_TYP:
        if data.get("actor") is None:
            raise jwt.InvalidTokenError("impersonation token missing actor")
        return data
    raise jwt.InvalidTokenError("not an access token")


def is_impersonation_token_payload(payload: dict) -> bool:
    """True if JWT claims represent a dev impersonation access token."""
    return payload.get("typ") == ACCESS_IMPERSONATION_TYP


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
