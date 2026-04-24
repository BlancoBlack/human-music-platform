from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.core.database import Base


class UserProfile(Base):
    """One row per user (optional until onboarding creates it)."""

    __tablename__ = "user_profiles"

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    display_name = Column(String(255), nullable=False)
    avatar_url = Column(String(512), nullable=True)
    bio = Column(String(1024), nullable=True)
    preferred_genres = Column(JSON, nullable=True)
    preferred_artists = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    user = relationship("User", back_populates="profile")
