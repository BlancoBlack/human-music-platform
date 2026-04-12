"""Shared refresh JWT + DB row validation (rotation and logout)."""

from __future__ import annotations

import logging
from datetime import datetime

import jwt
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.jwt_tokens import decode_refresh_token
from app.models.refresh_token import RefreshToken
from app.models.user import User

logger = logging.getLogger(__name__)


def refresh_auth_fail(
    client_detail: str, *, log_detail: str, extra: dict | None = None
) -> None:
    logger.info(
        "auth_refresh_failure",
        extra={"detail": log_detail, **(extra or {})},
    )
    raise HTTPException(status_code=401, detail=client_detail)


def assert_refresh_row_unexpired_unrevoked(
    row: RefreshToken | None,
    *,
    jti: str,
    user_id: int,
    now: datetime,
) -> RefreshToken:
    """Ensure the stored refresh row exists, is not revoked, and is not past ``expires_at``."""
    if row is None:
        refresh_auth_fail(
            "Unknown refresh token",
            log_detail="unknown_jti",
            extra={"jti": jti, "user_id": user_id},
        )
    if row.revoked_at is not None:
        refresh_auth_fail(
            "Refresh token revoked",
            log_detail="already_revoked",
            extra={"jti": jti, "user_id": user_id},
        )
    if row.expires_at < now:
        refresh_auth_fail(
            "Refresh token expired",
            log_detail="db_expired",
            extra={"jti": jti, "user_id": user_id},
        )
    return row


def validate_refresh_row_and_user(
    db: Session,
    *,
    row: RefreshToken | None,
    jti: str,
    user_id: int,
    now: datetime,
) -> User:
    """
    Validate a refresh-token DB row and resolve an active user.

    Shared by ``POST /auth/refresh`` (before rotation).
    """
    assert_refresh_row_unexpired_unrevoked(row, jti=jti, user_id=user_id, now=now)

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        refresh_auth_fail(
            "User not available",
            log_detail="user_missing",
            extra={"user_id": user_id},
        )
    if not user.is_active:
        logger.info(
            "auth_refresh_failure",
            extra={"detail": "inactive_user", "user_id": user_id},
        )
        raise HTTPException(status_code=403, detail="Inactive user")
    return user


def load_refresh_token_row_for_revocation(db: Session, raw: str) -> RefreshToken:
    """
    Decode refresh JWT and return the valid DB row (no user/active checks).

    Used by ``POST /auth/logout`` so inactive accounts can still end the session.
    """
    raw = (raw or "").strip()
    if not raw:
        refresh_auth_fail("Missing refresh token", log_detail="missing_token")
    try:
        payload = decode_refresh_token(raw)
    except jwt.PyJWTError:
        refresh_auth_fail(
            "Invalid or expired refresh token",
            log_detail="jwt_decode_error",
        )
    jti = str(payload["jti"])
    user_id = int(payload["sub"])
    now = datetime.utcnow()
    row = (
        db.query(RefreshToken)
        .filter(RefreshToken.jti == jti, RefreshToken.user_id == user_id)
        .first()
    )
    return assert_refresh_row_unexpired_unrevoked(
        row, jti=jti, user_id=user_id, now=now
    )
