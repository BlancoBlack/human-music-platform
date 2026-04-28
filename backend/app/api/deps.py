"""Shared FastAPI dependencies (auth, DB).

Streaming/listening endpoints use ``Authorization: Bearer <access_token>`` (same JWT
as ``/auth/login``).

The deprecated ``X-User-Id`` header is accepted only when ``ENABLE_LEGACY_AUTH=true``.
**Default is ``false``** — do not enable in production; it bypasses cryptographic proof
of identity.
"""

from __future__ import annotations

import logging
from typing import Annotated, TypedDict

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
from app.models.artist import Artist
from app.models.label import Label
from app.models.release import Release
from app.models.release_participant import ReleaseParticipant
from app.models.song import Song
from app.models.user import VALID_CONTEXT_TYPES, User
from app.models.user_role import UserRole
from app.services.artist_access_service import get_artist_owner_id
from app.services.rbac_service import has_permission, validate_role_exists

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)


class StudioContext(TypedDict):
    type: str
    id: int


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


def require_permission(permission_name: str):
    name = (permission_name or "").strip()

    async def _dependency(
        user: Annotated[User, Depends(get_current_user)],
        db: Annotated[Session, Depends(get_db)],
    ) -> User:
        if not has_permission(user, name, db=db):
            raise HTTPException(
                status_code=403,
                detail=f"Missing required permission: {name}",
            )
        return user

    return _dependency


def _has_artist_admin_override(user: User, db: Session) -> bool:
    return has_permission(user, "admin_full_access", db=db) or has_permission(
        user, "edit_any_artist", db=db
    )


def _has_user_admin_override(user: User, db: Session) -> bool:
    if has_permission(user, "admin_full_access", db=db):
        return True
    return (
        db.query(UserRole.id)
        .filter(UserRole.user_id == int(user.id), UserRole.role == "admin")
        .first()
        is not None
    )


def enforce_artist_ownership(
    *,
    artist_id: int,
    user: User,
    db: Session,
) -> Artist:
    artist = db.query(Artist).filter(Artist.id == int(artist_id)).first()
    if artist is None:
        raise HTTPException(status_code=404, detail="Artist not found")
    if _has_artist_admin_override(user, db):
        return artist
    owner_id = get_artist_owner_id(artist)
    if owner_id is None or int(owner_id) != int(user.id):
        raise HTTPException(status_code=403, detail="Not owner of this artist")
    return artist


async def require_artist_owner(
    artist_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Artist:
    return enforce_artist_ownership(artist_id=int(artist_id), user=user, db=db)


async def require_song_owner(
    song_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Song:
    song = (
        db.query(Song)
        .filter(Song.id == int(song_id), Song.deleted_at.is_(None))
        .first()
    )
    if song is None:
        raise HTTPException(status_code=404, detail="Song not found")
    enforce_artist_ownership(artist_id=int(song.artist_id), user=user, db=db)
    return song


async def require_release_owner(
    release_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Release:
    release = db.query(Release).filter(Release.id == int(release_id)).first()
    if release is None:
        raise HTTPException(status_code=404, detail="Release not found")
    enforce_artist_ownership(artist_id=int(release.artist_id), user=user, db=db)
    return release


def enforce_participant_actor(
    *,
    release_id: int,
    artist_id: int,
    user: User,
    db: Session,
) -> ReleaseParticipant:
    enforce_artist_ownership(artist_id=int(artist_id), user=user, db=db)
    participant = (
        db.query(ReleaseParticipant)
        .filter(
            ReleaseParticipant.release_id == int(release_id),
            ReleaseParticipant.artist_id == int(artist_id),
        )
        .first()
    )
    if participant is None:
        raise HTTPException(status_code=404, detail="Participant not found on this release")
    return participant


async def require_participant_actor(
    release_id: int,
    artist_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ReleaseParticipant:
    return enforce_participant_actor(
        release_id=int(release_id),
        artist_id=int(artist_id),
        user=user,
        db=db,
    )


async def require_self_or_admin(
    user_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    if int(user.id) == int(user_id):
        return user
    if _has_user_admin_override(user, db):
        return user
    raise HTTPException(status_code=403, detail="Not allowed to access this user")


async def require_admin_user(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    if not validate_role_exists("admin", db=db):
        raise HTTPException(status_code=403, detail="Admin role is not configured")
    is_admin = (
        db.query(UserRole.id)
        .filter(UserRole.user_id == int(user.id), UserRole.role == "admin")
        .first()
        is not None
    )
    if not is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def _owned_artist_ids_for_user(db: Session, user_id: int) -> set[int]:
    rows = (
        db.query(Artist.id)
        .filter(Artist.owner_user_id == int(user_id))
        .all()
    )
    return {int(row[0]) for row in rows}


def _owned_label_ids_for_user(db: Session, user_id: int) -> set[int]:
    rows = (
        db.query(Label.id)
        .filter(Label.owner_user_id == int(user_id))
        .all()
    )
    return {int(row[0]) for row in rows}


def is_context_allowed_for_user(
    *,
    db: Session,
    user: User,
    context_type: str,
    context_id: int,
) -> bool:
    ctype = str(context_type or "").strip().lower()
    cid = int(context_id)
    if ctype == "user":
        return int(user.id) == cid
    if ctype == "artist":
        return cid in _owned_artist_ids_for_user(db, int(user.id))
    if ctype == "label":
        return cid in _owned_label_ids_for_user(db, int(user.id))
    return False


def validate_context_for_user_or_403(
    *,
    db: Session,
    user: User,
    context_type: str,
    context_id: int,
) -> StudioContext:
    ctype = str(context_type or "").strip().lower()
    if ctype not in VALID_CONTEXT_TYPES:
        raise HTTPException(status_code=400, detail="Invalid context type")
    cid = int(context_id)
    if not is_context_allowed_for_user(
        db=db,
        user=user,
        context_type=ctype,
        context_id=cid,
    ):
        raise HTTPException(status_code=403, detail="Context not allowed for this user")
    return {"type": ctype, "id": cid}


def get_current_context(
    *,
    db: Session,
    user: User,
) -> StudioContext:
    stored_type = getattr(user, "current_context_type", None)
    stored_id = getattr(user, "current_context_id", None)
    if stored_type is not None and stored_id is not None:
        ctype = str(stored_type).strip().lower()
        if ctype in VALID_CONTEXT_TYPES:
            try:
                return validate_context_for_user_or_403(
                    db=db,
                    user=user,
                    context_type=ctype,
                    context_id=int(stored_id),
                )
            except HTTPException as exc:
                if int(exc.status_code) != 403:
                    raise
    return {"type": "user", "id": int(user.id)}
