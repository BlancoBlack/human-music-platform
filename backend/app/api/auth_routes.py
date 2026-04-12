"""JWT authentication: register, login, refresh, logout, /me."""

from __future__ import annotations

import logging
from datetime import datetime

import jwt
from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.auth_cookies import (
    REFRESH_COOKIE_NAME,
    attach_refresh_cookie,
    clear_refresh_cookie,
)
from app.api.deps import get_current_user
from app.core.auth_config import is_dev_impersonation_enabled
from app.core.database import get_db
from app.core.jwt_tokens import (
    create_access_token,
    create_impersonation_access_token,
    create_refresh_token,
    decode_refresh_token,
    new_refresh_jti,
)
from app.core.refresh_token_validate import (
    load_refresh_token_row_for_revocation,
    refresh_auth_fail,
    validate_refresh_row_and_user,
)
from app.core.security import verify_password
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.models.user_role import UserRole
from app.services.user_service import create_user, normalize_registration_email

logger = logging.getLogger(__name__)

router = APIRouter()


class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        return normalize_registration_email(v)


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        return normalize_registration_email(v)


class RefreshRequest(BaseModel):
    """Body optional when the browser sends the httpOnly refresh cookie."""

    refresh_token: str | None = None


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class TokenResponse(BaseModel):
    """OAuth-style token pair returned by register, login, and refresh.

    ``refresh_token`` in this JSON body exists for **tests** and **non-browser**
    clients (mobile apps, CLI) that cannot use cookies. **Browser clients must
    not** read or store ``refresh_token`` from JSON: they must rely on the
    **httpOnly** ``hm_refresh_token`` cookie (path ``/auth``) as the sole refresh
    credential to avoid XSS exfiltration and double-rotation bugs.
    """

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class ImpersonationState(BaseModel):
    actor_id: int
    actor_email: str | None = None


class UserMeResponse(BaseModel):
    id: int
    email: str | None
    is_active: bool
    is_email_verified: bool
    display_name: str | None
    roles: list[str]
    impersonation: ImpersonationState | None = None

    model_config = {"from_attributes": False}


class ImpersonateRequest(BaseModel):
    target_user_id: int = Field(..., ge=1, description="User id to act as (dev only)")


class ImpersonationAccessResponse(BaseModel):
    access_token: str
    impersonation: bool = True


def _issue_tokens(db: Session, user: User) -> TokenResponse:
    jti = new_refresh_jti()
    refresh_token, expires_at = create_refresh_token(user.id, jti)
    row = RefreshToken(jti=jti, user_id=user.id, expires_at=expires_at)
    db.add(row)
    db.flush()
    access = create_access_token(user.id)
    return TokenResponse(
        access_token=access,
        refresh_token=refresh_token,
        token_type="bearer",
    )


@router.post("/register", response_model=TokenResponse)
def auth_register(
    body: RegisterRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> TokenResponse:
    # TODO(economics): After email verification ships, require verified email for
    # withdrawal / payout-destination changes (see User.is_email_verified).
    if db.query(User.id).filter(User.email == body.email).first() is not None:
        raise HTTPException(status_code=400, detail="Email already registered")

    display_name = body.email.split("@")[0][:255] or "User"
    try:
        user = create_user(db, body.email, body.password, display_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Email already registered") from None

    try:
        tokens = _issue_tokens(db, user)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Email already registered") from None
    except Exception:
        logger.exception("auth_register_failed")
        db.rollback()
        raise HTTPException(status_code=500, detail="Registration failed") from None
    attach_refresh_cookie(response, tokens.refresh_token)
    return tokens


@router.post("/login", response_model=TokenResponse)
def auth_login(
    body: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> TokenResponse:
    # Unverified email must NOT block login (MVP). Gate money movement elsewhere later.
    user = db.query(User).filter(User.email == body.email).first()
    if user is None or not verify_password(body.password, user.password_hash or ""):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Inactive user")
    try:
        tokens = _issue_tokens(db, user)
        db.commit()
    except Exception:
        logger.exception("auth_login_failed")
        db.rollback()
        raise HTTPException(status_code=500, detail="Login failed") from None
    attach_refresh_cookie(response, tokens.refresh_token)
    return tokens


@router.get("/me", response_model=UserMeResponse)
def auth_me(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserMeResponse:
    profile = user.profile
    roles_q = (
        db.query(UserRole.role)
        .filter(UserRole.user_id == user.id)
        .order_by(UserRole.id)
        .all()
    )
    roles = [r[0] for r in roles_q]
    imp: ImpersonationState | None = None
    actor_id = getattr(request.state, "impersonation_actor_id", None)
    if actor_id is not None:
        actor_row = db.query(User).filter(User.id == int(actor_id)).first()
        imp = ImpersonationState(
            actor_id=int(actor_id),
            actor_email=actor_row.email if actor_row else None,
        )
    return UserMeResponse(
        id=int(user.id),
        email=user.email,
        is_active=bool(user.is_active),
        is_email_verified=bool(user.is_email_verified),
        display_name=profile.display_name if profile else None,
        roles=roles,
        impersonation=imp,
    )


@router.post("/dev/impersonate", response_model=ImpersonationAccessResponse)
def auth_dev_impersonate(
    request: Request,
    body: ImpersonateRequest,
    actor: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImpersonationAccessResponse:
    """Mint a short-lived impersonation access JWT (development + flag only)."""
    if not is_dev_impersonation_enabled():
        raise HTTPException(
            status_code=403,
            detail="Dev impersonation is disabled",
        )
    if getattr(request.state, "impersonation_actor_id", None) is not None:
        raise HTTPException(
            status_code=400,
            detail="Cannot start impersonation while already impersonating",
        )

    target = db.query(User).filter(User.id == int(body.target_user_id)).first()
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if not target.is_active:
        raise HTTPException(status_code=403, detail="Inactive user")

    logger.info(
        "impersonation_started",
        extra={
            "actor_id": int(actor.id),
            "target_user_id": int(target.id),
            "timestamp": datetime.utcnow().isoformat() + "Z",
        },
    )
    access = create_impersonation_access_token(int(target.id), int(actor.id))
    return ImpersonationAccessResponse(access_token=access, impersonation=True)


def _select_refresh_row_for_rotation(
    db: Session, *, jti: str, user_id: int
) -> RefreshToken | None:
    """Load the refresh row inside the current transaction (same ``db`` session).

    PostgreSQL: ``SELECT ... FOR UPDATE`` so two concurrent refreshes cannot both
    pass validation before either revokes the row.

    SQLite (dev / default ``DATABASE_URL``): ``FOR UPDATE`` is not emitted; the DB
    does not provide real row-level locking, so concurrent requests can still race.
    Use PostgreSQL in production if strict single-flight rotation is required at the DB.
    """
    q = db.query(RefreshToken).filter(
        RefreshToken.jti == jti,
        RefreshToken.user_id == user_id,
    )
    if db.get_bind().dialect.name == "postgresql":
        return q.with_for_update().first()
    return q.first()


# WARNING:
#
# * Browser clients MUST NOT use refresh_token from JSON
# * Always rely on httpOnly cookie
#
# (JSON still includes refresh_token for tests and non-browser clients.)
@router.post("/refresh", response_model=TokenResponse)
def auth_refresh(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    body: RefreshRequest = Body(default_factory=RefreshRequest),
) -> TokenResponse:
    raw = (body.refresh_token or "").strip() or request.cookies.get(
        REFRESH_COOKIE_NAME
    )
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
    new_jti: str | None = None
    new_refresh: str | None = None
    new_access: str | None = None

    try:
        # One transaction, one commit (via ``begin()``): lock row → validate →
        # revoke → insert successor → mint access JWT. No ``flush``/``commit`` in between.
        with db.begin():
            now = datetime.utcnow()
            row = _select_refresh_row_for_rotation(db, jti=jti, user_id=user_id)
            user = validate_refresh_row_and_user(
                db, row=row, jti=jti, user_id=user_id, now=now
            )

            row.revoked_at = now
            new_jti = new_refresh_jti()
            new_refresh, expires_at = create_refresh_token(user_id, new_jti)
            db.add(
                RefreshToken(jti=new_jti, user_id=user_id, expires_at=expires_at),
            )
            new_access = create_access_token(user.id)
    except HTTPException:
        db.rollback()
        raise

    assert new_jti is not None and new_refresh is not None and new_access is not None
    logger.info(
        "auth_refresh_rotation",
        extra={
            "user_id": user_id,
            "old_jti": jti,
            "new_jti": new_jti,
        },
    )
    logger.info(
        "auth_refresh_success",
        extra={"user_id": user_id, "new_jti": new_jti},
    )

    attach_refresh_cookie(response, new_refresh)
    return TokenResponse(
        access_token=new_access,
        refresh_token=new_refresh,
        token_type="bearer",
    )


@router.post("/logout", status_code=204)
def auth_logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    body: LogoutRequest = Body(default_factory=LogoutRequest),
) -> None:
    raw = (body.refresh_token or "").strip() or request.cookies.get(
        REFRESH_COOKIE_NAME
    )
    if not raw:
        clear_refresh_cookie(response)
        return None
    try:
        row = load_refresh_token_row_for_revocation(db, raw)
    except HTTPException:
        clear_refresh_cookie(response)
        raise
    if row.revoked_at is None:
        row.revoked_at = datetime.utcnow()
    db.commit()
    clear_refresh_cookie(response)
    return None
