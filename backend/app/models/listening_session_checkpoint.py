from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, UniqueConstraint

from app.core.database import Base


class ListeningSessionCheckpoint(Base):
    __tablename__ = "listening_session_checkpoints"
    __table_args__ = (
        UniqueConstraint("session_id", "sequence", name="uq_session_checkpoint_sequence"),
        Index("ix_listening_session_checkpoints_session_id", "session_id"),
        Index("ix_listening_session_checkpoints_user_id_created_at", "user_id", "created_at"),
    )

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("listening_sessions.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    song_id = Column(Integer, ForeignKey("songs.id"), nullable=False)
    sequence = Column(Integer, nullable=False)
    position_seconds = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
