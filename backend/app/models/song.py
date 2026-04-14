from sqlalchemy import JSON, Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import relationship
from app.core.database import Base


SONG_STATE_DRAFT = "draft"
SONG_STATE_MEDIA_READY = "media_ready"
SONG_STATE_METADATA_READY = "metadata_ready"
SONG_STATE_ECONOMY_READY = "economy_ready"
SONG_STATE_READY_FOR_RELEASE = "ready_for_release"

SONG_STATE_VALUES = (
    SONG_STATE_DRAFT,
    SONG_STATE_MEDIA_READY,
    SONG_STATE_METADATA_READY,
    SONG_STATE_ECONOMY_READY,
    SONG_STATE_READY_FOR_RELEASE,
)


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
    state = Column(
        Enum(*SONG_STATE_VALUES, name="song_state_enum", native_enum=False),
        nullable=False,
        default=SONG_STATE_DRAFT,
    )
    genre_id = Column(Integer, ForeignKey("genres.id"), nullable=True)
    subgenre_id = Column(Integer, ForeignKey("subgenres.id"), nullable=True)
    moods = Column(
        ARRAY(String).with_variant(JSON, "sqlite"),
        nullable=True,
    )
    country_code = Column(String(2), nullable=True)
    city = Column(String(128), nullable=True)
    release_id = Column(Integer, ForeignKey("releases.id"), nullable=True)
    track_number = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=func.now())
    deleted_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, onupdate=func.now())

    artist = relationship("Artist")
    release = relationship("Release", back_populates="songs")
    genre = relationship("Genre")
    subgenre = relationship("Subgenre")
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