"""Shared FastAPI dependencies (auth, DB).

Listening ingestion migration (JWT vs X-User-Id):
- Prefer ``Authorization: Bearer <access_token>`` (same JWT as ``/auth/login``).
- If no bearer token is sent and ``ENABLE_LEGACY_AUTH`` is true (default), the
  ``X-User-Id`` header is still accepted; each use logs
  ``DEPRECATED AUTH METHOD USED`` with path, method, and user_id.
- Set ``ENABLE_LEGACY_AUTH=false`` to reject header-only auth (production target).
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
from app.core.jwt_tokens import decode_access_token
from app.models.user import User

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)


def _load_user_from_access_token(db: Session, token: str) -> User:
    """Validate access JWT and return User (raises HTTPException on failure)."""
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
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


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    if credentials is None or (credentials.scheme or "").lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = (credentials.credentials or "").strip()
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = _load_user_from_access_token(db, token)
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Inactive user")
    return user


def get_listening_user_id(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
    db: Session = Depends(get_db),
) -> int:
    """
    Authenticate streaming/listening requests: JWT first, then optional
    ``X-User-Id`` when legacy mode is enabled.
    """
    token: str | None = None
    if credentials is not None and (credentials.scheme or "").lower() == "bearer":
        token = (credentials.credentials or "").strip() or None

    if token is not None:
        user = _load_user_from_access_token(db, token)
        if not user.is_active:
            raise HTTPException(status_code=403, detail="Inactive user")
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
