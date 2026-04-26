"""Centralized creation of auth-backed users (User + profile + default role)."""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password, validate_password_for_bcrypt
from app.models.user import User
from app.models.user_profile import UserProfile
from app.services.rbac_service import assign_role_to_user

# Dev/seed scripts only — not used for interactive accounts in production.
SEED_LISTENER_PLACEHOLDER_PASSWORD = "seed-listener-password-do-not-use!!"
DEFAULT_ONBOARDING_STEP = "REGISTERED"


def normalize_registration_email(raw: str | None) -> str:
    """Normalize and validate email using the same rules as ``/auth/register``."""
    if raw is None:
        raise ValueError("Email is required")
    s = raw.strip().lower()
    if not s:
        raise ValueError("Email is required")
    if len(s) < 3:
        raise ValueError("Invalid email format")
    if "@" not in s:
        raise ValueError("Invalid email format")
    local, _, domain = s.partition("@")
    if not local or not domain or "." not in domain:
        raise ValueError("Invalid email format")
    if domain.startswith(".") or domain.endswith(".") or ".." in domain:
        raise ValueError("Invalid email format")
    return s


def create_user(
    db: Session,
    email: str,
    password: str,
    display_name: str,
    *,
    username: str | None = None,
    default_role_name: str | None = "user",
    onboarding_completed: bool = True,
    onboarding_step: str = DEFAULT_ONBOARDING_STEP,
) -> User:
    """Create ``User``, ``UserProfile``, and a default product role in one place.

    Persists the user row with ``flush`` so ``user.id`` is available for profile/role.
    Does **not** ``commit`` — callers own the transaction.

    ``username`` is optional legacy seed data; new registrations omit it.

    Raises:
        ValueError: missing/invalid email or password constraints.
        IntegrityError: duplicate email/username at flush (caller should rollback).
    """
    if email is None:
        raise ValueError("Email is required")

    normalized_email = normalize_registration_email(email)

    if not password or len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    validate_password_for_bcrypt(password)

    dn = (display_name or "").strip()[:255] or "User"

    user = User(
        email=normalized_email,
        password_hash=hash_password(password),
        is_active=True,
        is_email_verified=False,
        onboarding_completed=bool(onboarding_completed),
        onboarding_step=onboarding_step,
        username=username,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        raise

    db.add(UserProfile(user_id=user.id, display_name=dn))
    if default_role_name is not None:
        rbac_role_name = map_product_role_to_rbac(default_role_name)
        assign_role_to_user(db, user_id=int(user.id), role_name=rbac_role_name)
    return user


def map_product_role_to_rbac(role: str) -> str:
    """Map canonical product roles to current RBAC role names.

    Compatibility layer (temporary): product ``user`` maps to RBAC ``listener``.
    """
    normalized = (role or "").strip().lower()
    if normalized == "artist":
        return "artist"
    if normalized == "user":
        return "listener"
    raise ValueError("Invalid role")
