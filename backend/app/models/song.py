from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship
from app.core.database import Base


class Song(Base):
    __tablename__ = "songs"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    system_key = Column(String(64), unique=True, nullable=True)
    artist_id = Column(Integer, ForeignKey("artists.id"))
    is_system = Column(Boolean, default=False, nullable=False)
    duration_seconds = Column(Integer, nullable=True)
    file_path = Column(String, nullable=True)
    upload_status = Column(String, default="draft")
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    artist = relationship("Artist")
    featured_artists = relationship(
        "SongFeaturedArtist",
        back_populates="song",
        cascade="all, delete-orphan",
        order_by="SongFeaturedArtist.position",
    )
    credit_entries = relationship(
        "SongCreditEntry",
        back_populates="song",
        cascade="all, delete-orphan",
        order_by="SongCreditEntry.position",
    )