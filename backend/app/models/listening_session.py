from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from app.core.database import Base


class ListeningSession(Base):
    __tablename__ = "listening_sessions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    song_id = Column(Integer, ForeignKey("songs.id"), nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    total_duration = Column(Integer, default=0)
    finalized_at = Column(DateTime, nullable=True)
    discovery_request_id = Column(String(64), nullable=True)
    discovery_section = Column(String(32), nullable=True)
    discovery_position = Column(Integer, nullable=True)
    # Playback attribution. Not used by payout snapshots or validation.
    # ORM default aligns with implicit /stream session creation (always set in services).
    source_type = Column(String(32), nullable=True, default="direct")
    source_id = Column(String(128), nullable=True)

