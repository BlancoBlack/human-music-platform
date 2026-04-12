"""Centralized creation of auth-backed users (User + profile + default role)."""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.user import User
from app.models.user_profile import UserProfile
from app.models.user_role import UserRole

# Dev/seed scripts only — not used for interactive accounts in production.
SEED_LISTENER_PLACEHOLDER_PASSWORD = "seed-listener-password-do-not-use!!"


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
) -> User:
    """Create ``User``, ``UserProfile``, and default ``listener`` role in one place.

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
    if len(password) > 128:
        raise ValueError("Password must be at most 128 characters")

    dn = (display_name or "").strip()[:255] or "User"

    user = User(
        email=normalized_email,
        password_hash=hash_password(password),
        is_active=True,
        is_email_verified=False,
        username=username,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        raise

    db.add(UserProfile(user_id=user.id, display_name=dn))
    db.add(UserRole(user_id=user.id, role="listener"))
    return user
