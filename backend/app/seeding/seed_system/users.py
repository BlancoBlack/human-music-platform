from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.models.user import User
from app.models.user_profile import UserProfile
from app.services.rbac_service import assign_role_to_user, ensure_default_roles
from app.services.user_service import SEED_LISTENER_PLACEHOLDER_PASSWORD, create_user

SEED_ADMIN_EMAIL = "borja@hellosamples.com"
SEED_ADMIN_USERNAME = "admin"
SEED_ADMIN_PASSWORD = "69476947"


def _username(first: str, last: str) -> str:
    return f"{first}.{last}".replace(" ", "").replace("'", "").lower()


def _display_name(first: str, last: str) -> str:
    return f"{first} {last}".strip()


def upsert_seed_users(db: Session, profiles: Sequence[dict[str, object]]) -> list[User]:
    ensure_default_roles(db)
    admin_user = _upsert_seed_admin_user(db)
    users: list[User] = []
    for profile in profiles:
        first = str(profile["first"])
        last = str(profile["last"])
        username = _username(first, last)
        email = f"{username}@seed.hmp.local"
        display_name = _display_name(first, last)
        onboarding_step = str(profile["onboarding_step"])
        onboarding_completed = bool(profile["onboarding_completed"])

        row = db.query(User).filter(User.email == email).one_or_none()
        if row is None:
            row = create_user(
                db,
                email=email,
                password=SEED_LISTENER_PLACEHOLDER_PASSWORD,
                display_name=display_name,
                username=username,
                onboarding_completed=onboarding_completed,
            )
            row.onboarding_step = onboarding_step
            if onboarding_completed:
                row.sub_role = "listener"
        else:
            row.username = username
            row.onboarding_step = onboarding_step
            row.onboarding_completed = onboarding_completed
            row.sub_role = "listener" if onboarding_completed else row.sub_role
            profile_row = row.profile
            if profile_row is None:
                profile_row = UserProfile(user_id=int(row.id), display_name=display_name)
                db.add(profile_row)
            else:
                profile_row.display_name = display_name
            assign_role_to_user(db, user_id=int(row.id), role_name="listener")
        db.flush()
        users.append(row)
    # Keep deterministic ordering: admin inserted first, then listener users.
    # This allows seed artist owner_user_id alignment with artist IDs when
    # treasury occupies artist_id=1.
    if admin_user is None:
        raise RuntimeError("Seed admin user missing after upsert.")
    return users


def _upsert_seed_admin_user(db: Session) -> User:
    display_name = "Borja Admin"
    row = db.query(User).filter(User.email == SEED_ADMIN_EMAIL).one_or_none()
    if row is None:
        row = create_user(
            db,
            email=SEED_ADMIN_EMAIL,
            password=SEED_ADMIN_PASSWORD,
            display_name=display_name,
            username=SEED_ADMIN_USERNAME,
            default_role_name=None,
            onboarding_completed=True,
        )
        row.onboarding_step = "COMPLETED"
    else:
        row.username = SEED_ADMIN_USERNAME
        row.onboarding_completed = True
        row.onboarding_step = "COMPLETED"
        profile_row = row.profile
        if profile_row is None:
            db.add(UserProfile(user_id=int(row.id), display_name=display_name))
        else:
            profile_row.display_name = display_name
    assign_role_to_user(db, user_id=int(row.id), role_name="admin")
    db.flush()
    return row
