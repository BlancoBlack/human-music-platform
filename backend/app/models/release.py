from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from app.core.database import Base


RELEASE_TYPE_SINGLE = "single"
RELEASE_TYPE_ALBUM = "album"
RELEASE_TYPE_VALUES = (
    RELEASE_TYPE_SINGLE,
    RELEASE_TYPE_ALBUM,
)

RELEASE_STATE_DRAFT = "draft"
RELEASE_STATE_SCHEDULED = "scheduled"
RELEASE_STATE_PUBLISHED = "published"
RELEASE_STATE_FROZEN = "frozen"
RELEASE_STATE_VALUES = (
    RELEASE_STATE_DRAFT,
    RELEASE_STATE_SCHEDULED,
    RELEASE_STATE_PUBLISHED,
    RELEASE_STATE_FROZEN,
)


class Release(Base):
    __tablename__ = "releases"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    artist_id = Column(Integer, ForeignKey("artists.id"), nullable=False, index=True)
    type = Column(
        Enum(*RELEASE_TYPE_VALUES, name="release_type_enum", native_enum=False),
        nullable=False,
    )
    release_date = Column(DateTime, nullable=False)
    discoverable_at = Column(DateTime, nullable=True)
    state = Column(
        Enum(*RELEASE_STATE_VALUES, name="release_state_enum", native_enum=False),
        nullable=False,
        default=RELEASE_STATE_DRAFT,
    )
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, onupdate=func.now())

    artist = relationship("Artist")
    songs = relationship("Song", back_populates="release")
    media_assets = relationship(
        "ReleaseMediaAsset",
        back_populates="release",
        cascade="all, delete-orphan",
    )
