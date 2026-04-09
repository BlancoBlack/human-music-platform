from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, UniqueConstraint

from app.core.database import Base


class IngestionLock(Base):
    """
    Serialize validate_listen + ListeningEvent insert per (user_id, song_id).
    Rows are upserted (locked_at bumped); the table carries no business meaning.
    """

    __tablename__ = "ingestion_locks"
    __table_args__ = (
        UniqueConstraint("user_id", "song_id", name="uq_ingestion_locks_user_song"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    song_id = Column(Integer, nullable=False)
    locked_at = Column(DateTime, default=datetime.utcnow, nullable=False)
