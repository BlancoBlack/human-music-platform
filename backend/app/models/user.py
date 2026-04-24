from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import relationship

from app.core.database import Base


class User(Base):
    """
    Platform user. The `users` table is referenced by listening, balances, etc.

    ``username`` is legacy; new auth flows should use ``email``. ``email`` is
    nullable at the DB layer on SQLite until legacy rows are backfilled (see
    ``ensure_auth_user_schema``); application code should treat it as required
    for new registrations.

    TODO(product + economics): When payouts / withdrawals are user-linked,
    require ``is_email_verified`` before allowing withdrawal or settlement to a
    new destination. Until then, unverified users may still log in (see
    ``/auth/login``).
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=True)
    email = Column(String(255), unique=True, index=True, nullable=True)
    password_hash = Column(String(255), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    # TODO(economics): Block payout wallet changes for ``is_email_verified`` is False.
    is_email_verified = Column(Boolean, nullable=False, default=False)
    onboarding_completed = Column(Boolean, nullable=False, default=True)
    onboarding_step = Column(String(64), nullable=True)
    sub_role = Column(String(32), nullable=True)
    created_at = Column(DateTime, nullable=True, default=datetime.utcnow)

    profile = relationship(
        "UserProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    user_role_entries = relationship(
        "UserRole",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    roles = relationship(
        "Role",
        secondary="user_roles",
        primaryjoin="User.id == foreign(UserRole.user_id)",
        secondaryjoin="foreign(UserRole.role) == Role.name",
        viewonly=True,
    )
    linked_artists = relationship(
        "Artist",
        back_populates="user",
        foreign_keys="Artist.user_id",
    )
    owned_artists = relationship(
        "Artist",
        back_populates="owner",
        foreign_keys="Artist.owner_user_id",
    )
    owned_labels = relationship(
        "Label",
        back_populates="owner",
        foreign_keys="Label.owner_user_id",
    )
    refresh_tokens = relationship(
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )
