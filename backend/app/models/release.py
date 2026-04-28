from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from app.core.database import Base


RELEASE_TYPE_SINGLE = "single"
RELEASE_TYPE_ALBUM = "album"
RELEASE_TYPE_EP = "ep"
RELEASE_TYPE_VALUES = (
    RELEASE_TYPE_SINGLE,
    RELEASE_TYPE_ALBUM,
    RELEASE_TYPE_EP,
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

RELEASE_APPROVAL_STATUS_DRAFT = "draft"
RELEASE_APPROVAL_STATUS_PENDING = "pending_approvals"
RELEASE_APPROVAL_STATUS_READY = "ready"
RELEASE_APPROVAL_STATUS_VALUES = (
    RELEASE_APPROVAL_STATUS_DRAFT,
    RELEASE_APPROVAL_STATUS_PENDING,
    RELEASE_APPROVAL_STATUS_READY,
)


class Release(Base):
    __tablename__ = "releases"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String(255), nullable=False, unique=True, index=True)
    title = Column(String(255), nullable=False)
    artist_id = Column(Integer, ForeignKey("artists.id"), nullable=False, index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
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
    approval_status = Column(
        Enum(*RELEASE_APPROVAL_STATUS_VALUES, name="release_approval_status_enum", native_enum=False),
        nullable=False,
        default=RELEASE_APPROVAL_STATUS_DRAFT,
    )
    split_version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, onupdate=func.now())

    artist = relationship("Artist")
    owner = relationship(
        "User",
        foreign_keys=[owner_user_id],
        back_populates="owned_releases",
    )
    songs = relationship("Song", back_populates="release")
    participants = relationship(
        "ReleaseParticipant",
        back_populates="release",
        cascade="all, delete-orphan",
    )
    media_assets = relationship(
        "ReleaseMediaAsset",
        back_populates="release",
        cascade="all, delete-orphan",
    )
