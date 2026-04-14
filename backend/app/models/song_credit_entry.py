from sqlalchemy import CheckConstraint, Column, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.database import Base

# Stored values must match API / CHECK below (human-readable roles).
CREDIT_ROLE_VALUES = (
    "songwriter",
    "composer",
    "arranger",
    "producer",
    "musician",
    "sound designer",
    "mix engineer",
    "mastering engineer",
    "artwork",
    "studio",
)
_CREDIT_ROLE_IN_CLAUSE = ", ".join(repr(v) for v in CREDIT_ROLE_VALUES)


class SongCreditEntry(Base):
    __tablename__ = "song_credit_entries"
    __table_args__ = (
        UniqueConstraint("song_id", "position", name="uq_song_credit_entries_song_position"),
        CheckConstraint(
            "position >= 1 AND position <= 20",
            name="ck_song_credit_entries_position",
        ),
        CheckConstraint(
            f"role IN ({_CREDIT_ROLE_IN_CLAUSE})",
            name="ck_song_credit_entries_role",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    song_id = Column(Integer, ForeignKey("songs.id", ondelete="CASCADE"), nullable=False, index=True)
    position = Column(Integer, nullable=False)
    display_name = Column(String(512), nullable=False)
    role = Column(String(64), nullable=False)

    song = relationship("Song", back_populates="credit_entries")
