from sqlalchemy import CheckConstraint, Column, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.database import Base


class SongFeaturedArtist(Base):
    __tablename__ = "song_featured_artists"
    __table_args__ = (
        UniqueConstraint("song_id", "artist_id", name="uq_song_featured_artists_song_artist"),
        UniqueConstraint("song_id", "position", name="uq_song_featured_artists_song_position"),
        CheckConstraint("position >= 1 AND position <= 20", name="ck_song_featured_artists_position"),
    )

    id = Column(Integer, primary_key=True, index=True)
    song_id = Column(Integer, ForeignKey("songs.id", ondelete="CASCADE"), nullable=False, index=True)
    artist_id = Column(Integer, ForeignKey("artists.id"), nullable=False, index=True)
    position = Column(Integer, nullable=False)

    song = relationship("Song", back_populates="featured_artists")
    artist = relationship("Artist")
