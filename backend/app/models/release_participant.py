from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import relationship

from app.core.database import Base

RELEASE_PARTICIPANT_ROLE_PRIMARY = "primary"
RELEASE_PARTICIPANT_ROLE_COLLABORATOR = "collaborator"
RELEASE_PARTICIPANT_ROLE_FEATURED = "featured"
RELEASE_PARTICIPANT_ROLE_VALUES = (
    RELEASE_PARTICIPANT_ROLE_PRIMARY,
    RELEASE_PARTICIPANT_ROLE_COLLABORATOR,
    RELEASE_PARTICIPANT_ROLE_FEATURED,
)

RELEASE_PARTICIPANT_STATUS_PENDING = "pending"
RELEASE_PARTICIPANT_STATUS_ACCEPTED = "accepted"
RELEASE_PARTICIPANT_STATUS_REJECTED = "rejected"
RELEASE_PARTICIPANT_STATUS_VALUES = (
    RELEASE_PARTICIPANT_STATUS_PENDING,
    RELEASE_PARTICIPANT_STATUS_ACCEPTED,
    RELEASE_PARTICIPANT_STATUS_REJECTED,
)

RELEASE_PARTICIPANT_APPROVAL_TYPE_SPLIT = "split"
RELEASE_PARTICIPANT_APPROVAL_TYPE_FEATURE = "feature"
RELEASE_PARTICIPANT_APPROVAL_TYPE_NONE = "none"
RELEASE_PARTICIPANT_APPROVAL_TYPE_VALUES = (
    RELEASE_PARTICIPANT_APPROVAL_TYPE_SPLIT,
    RELEASE_PARTICIPANT_APPROVAL_TYPE_FEATURE,
    RELEASE_PARTICIPANT_APPROVAL_TYPE_NONE,
)


class ReleaseParticipant(Base):
    __tablename__ = "release_participants"
    __table_args__ = (
        UniqueConstraint(
            "release_id",
            "artist_id",
            name="uq_release_participants_release_artist",
        ),
        CheckConstraint(
            "role IN ('primary','collaborator','featured')",
            name="ck_release_participants_role_values",
        ),
        CheckConstraint(
            "status IN ('pending','accepted','rejected')",
            name="ck_release_participants_status_values",
        ),
        CheckConstraint(
            "approval_type IN ('split','feature','none')",
            name="ck_release_participants_approval_type_values",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    release_id = Column(
        Integer,
        ForeignKey("releases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    artist_id = Column(Integer, ForeignKey("artists.id"), nullable=False, index=True)
    role = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False)
    requires_approval = Column(Boolean, nullable=False, default=True)
    approval_type = Column(String(16), nullable=False, default=RELEASE_PARTICIPANT_APPROVAL_TYPE_SPLIT)
    approved_at = Column(DateTime, nullable=True)
    approved_split_version = Column(Integer, nullable=True)
    rejection_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())

    release = relationship("Release", back_populates="participants")
    artist = relationship("Artist")
