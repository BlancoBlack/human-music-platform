from __future__ import annotations

import logging
from collections.abc import Iterable
from collections.abc import Collection

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.permission import Permission
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.user import User
from app.models.user_role import UserRole

logger = logging.getLogger(__name__)

RBAC_DEFAULT_ROLE_NAMES: tuple[str, ...] = ("admin", "artist", "label", "listener")


def validate_role_exists(role_name: str, db: Session | None = None) -> bool:
    name = (role_name or "").strip()
    if not name:
        return False
    owns_session = db is None
    session = db or SessionLocal()
    try:
        return (
            session.query(Role.id)
            .filter(Role.name == name)
            .first()
            is not None
        )
    finally:
        if owns_session:
            session.close()


def ensure_role_exists(role_name: str, db: Session) -> Role:
    name = (role_name or "").strip()
    if not name:
        raise ValueError("Role name is required")
    row = db.query(Role).filter(Role.name == name).first()
    if row is None:
        row = Role(name=name)
        db.add(row)
        db.flush()
    return row


def ensure_default_roles(db: Session) -> None:
    for role_name in RBAC_DEFAULT_ROLE_NAMES:
        ensure_role_exists(role_name, db)


def assign_role_to_user(
    db: Session,
    *,
    user_id: int,
    role_name: str,
) -> UserRole:
    name = (role_name or "").strip()
    if not name:
        raise ValueError("Role name is required")
    if not validate_role_exists(name, db=db):
        raise ValueError(f"Unknown role: {name}")
    existing = (
        db.query(UserRole.id)
        .filter(UserRole.user_id == int(user_id), UserRole.role == name)
        .first()
    )
    if existing is not None:
        return (
            db.query(UserRole)
            .filter(UserRole.user_id == int(user_id), UserRole.role == name)
            .first()
        )
    row = UserRole(user_id=int(user_id), role=name)
    db.add(row)
    return row


def get_invalid_user_roles(user_id: int, db: Session | None = None) -> list[str]:
    owns_session = db is None
    session = db or SessionLocal()
    try:
        rows = (
            session.query(UserRole.role)
            .outerjoin(Role, Role.name == UserRole.role)
            .filter(UserRole.user_id == int(user_id), Role.id.is_(None))
            .order_by(UserRole.id.asc())
            .all()
        )
        invalid_roles = [str(role_name) for (role_name,) in rows]
        if invalid_roles:
            logger.warning(
                "rbac_user_has_invalid_roles",
                extra={"user_id": int(user_id), "invalid_roles": invalid_roles},
            )
        return invalid_roles
    finally:
        if owns_session:
            session.close()


def _permission_rows_for_user(db: Session, user_id: int) -> Iterable[tuple[str]]:
    return (
        db.query(Permission.name)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(Role, Role.id == RolePermission.role_id)
        .join(UserRole, UserRole.role == Role.name)
        .filter(UserRole.user_id == int(user_id))
        .distinct()
        .order_by(Permission.name.asc())
        .all()
    )


def get_user_permissions(user_id: int, db: Session | None = None) -> list[str]:
    owns_session = db is None
    session = db or SessionLocal()
    try:
        rows = _permission_rows_for_user(session, int(user_id))
        return [str(name) for (name,) in rows]
    finally:
        if owns_session:
            session.close()


def has_permission(
    user: User,
    permission_name: str,
    db: Session | None = None,
    user_permissions: Collection[str] | None = None,
) -> bool:
    name = (permission_name or "").strip()
    if not name:
        return False
    perms = list(user_permissions) if user_permissions is not None else get_user_permissions(
        int(user.id), db=db
    )
    return name in perms
