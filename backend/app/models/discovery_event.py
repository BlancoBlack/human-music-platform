from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Index, Integer, String

from app.core.database import Base


class DiscoveryEvent(Base):
    __tablename__ = "discovery_events"
    __table_args__ = (
        Index("ix_discovery_events_created_at", "created_at"),
        Index("ix_discovery_events_event_type_created_at", "event_type", "created_at"),
        Index("ix_discovery_events_request_id", "request_id"),
        Index("ix_discovery_events_song_id_created_at", "song_id", "created_at"),
        Index("ix_discovery_events_user_id_created_at", "user_id", "created_at"),
    )

    id = Column(Integer, primary_key=True)
    event_type = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    request_id = Column(String(64), nullable=False)

    song_id = Column(Integer, nullable=True)
    artist_id = Column(Integer, nullable=True)
    section = Column(String(32), nullable=True)
    position = Column(Integer, nullable=True)

    metadata_json = Column(JSON, nullable=False, default=dict)
