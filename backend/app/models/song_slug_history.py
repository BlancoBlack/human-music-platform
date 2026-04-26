from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, func

from app.core.database import Base


class SongSlugHistory(Base):
    __tablename__ = "song_slug_history"

    id = Column(Integer, primary_key=True, index=True)
    song_id = Column(
        Integer,
        ForeignKey("songs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    slug = Column(String(255), nullable=False, unique=True, index=True)
    is_current = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
