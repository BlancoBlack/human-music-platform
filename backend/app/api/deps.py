"""Shared FastAPI dependencies (auth, DB).

Streaming/listening endpoints use ``Authorization: Bearer <access_token>`` (same JWT
as ``/auth/login``).

The deprecated ``X-User-Id`` header is accepted only when ``ENABLE_LEGACY_AUTH=true``.
**Default is ``false``** — do not enable in production; it bypasses cryptographic proof
of identity.
"""

from __future__ import annotations

import logging
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.auth_config import is_legacy_header_auth_enabled
from app.core.database import get_db
from app.core.jwt_tokens import (
    decode_access_token,
    is_impersonation_token_payload,
)
from app.models.user import User

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)


def _bearer_token_from_credentials(
    credentials: HTTPAuthorizationCredentials | None,
) -> str | None:
    if credentials is None or (credentials.scheme or "").lower() != "bearer":
        return None
    token = (credentials.credentials or "").strip()
    return token or None


def _user_from_access_payload(db: Session, payload: dict) -> User:
    """Map decoded access (or impersonation access) claims to a ``User`` row."""
    try:
        user_id = int(payload["sub"])
    except (TypeError, ValueError, KeyError):
        raise HTTPException(
            status_code=401,
            detail="Invalid token subject",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def resolve_user_from_access_token(
    request: Request,
    db: Session,
    token: str,
) -> User:
    """
    Decode access JWT (including impersonation typ), set ``request.state`` impersonation
    metadata, load user, enforce ``is_active``.
    """
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    request.state.impersonation_actor_id = None
    if is_impersonation_token_payload(payload):
        try:
            request.state.impersonation_actor_id = int(payload["actor"])
        except (TypeError, ValueError, KeyError):
            request.state.impersonation_actor_id = None
    user = _user_from_access_payload(db, payload)
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Inactive user")
    return user


async def require_non_impersonation(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> None:
    """
    Reject requests that present an impersonation access JWT on ``Authorization``.
    Use on payout, wallet, or admin-mutation routes when Bearer auth is present.
    """
    if credentials is None or (credentials.scheme or "").lower() != "bearer":
        return
    token = (credentials.credentials or "").strip()
    if not token:
        return
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError:
        return
    if is_impersonation_token_payload(payload):
        raise HTTPException(
            status_code=403,
            detail="This action is not allowed while impersonating another user",
        )


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    token = _bearer_token_from_credentials(credentials)
    if token is None:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return resolve_user_from_access_token(request, db, token)


def get_listening_user_id(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
    db: Session = Depends(get_db),
) -> int:
    """
    Authenticate streaming/listening requests: JWT first, then optional
    ``X-User-Id`` when legacy mode is explicitly enabled.
    """
    token = _bearer_token_from_credentials(credentials)

    if token is not None:
        user = resolve_user_from_access_token(request, db, token)
        return int(user.id)

    if is_legacy_header_auth_enabled():
        if x_user_id is None or str(x_user_id).strip() == "":
            raise HTTPException(status_code=401, detail="Not authenticated")
        try:
            uid = int(str(x_user_id).strip())
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=401, detail="Invalid X-User-Id header"
            ) from exc
        exists = db.query(User.id).filter(User.id == uid).first()
        if exists is None:
            raise HTTPException(status_code=401, detail="User not found")
        logger.warning(
            "DEPRECATED AUTH METHOD USED: X-User-Id header (use Bearer JWT). "
            "path=%s method=%s user_id=%s",
            request.url.path,
            request.method,
            uid,
        )
        return uid

    raise HTTPException(status_code=401, detail="Not authenticated")


async def get_optional_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Annotated[Session, Depends(get_db)],
) -> User | None:
    """
    Optional Bearer auth for read-only surfaces (e.g. discovery).

    - Missing or invalid token → ``None`` (no 401).
    - Valid token but unknown/inactive user → ``None``.
    - Valid active user (including impersonation subject) → ``User``.

    Sets ``request.state.impersonation_actor_id`` when the token is impersonation,
    same as ``resolve_user_from_access_token``, so downstream code can audit.
    """
    token = _bearer_token_from_credentials(credentials)
    if token is None:
        return None
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError:
        return None

    request.state.impersonation_actor_id = None
    if is_impersonation_token_payload(payload):
        try:
            request.state.impersonation_actor_id = int(payload["actor"])
        except (TypeError, ValueError, KeyError):
            request.state.impersonation_actor_id = None

    try:
        user_id = int(payload["sub"])
    except (TypeError, ValueError, KeyError):
        return None

    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.is_active:
        return None
    return user
