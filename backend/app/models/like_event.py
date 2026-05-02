"""Explicit user → song like events (separate from playlist organization)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.database import Base


class LikeEvent(Base):
    __tablename__ = "like_events"
    __table_args__ = (
        UniqueConstraint("user_id", "song_id", name="uq_like_events_user_song"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    song_id = Column(
        Integer,
        ForeignKey("songs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    user = relationship("User", backref="like_events")
    song = relationship("Song", backref="like_events")
