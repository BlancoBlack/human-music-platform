from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import relationship

from app.core.database import Base

# Stored in DB; keep in sync with CHECK constraint below.
SONG_MEDIA_KIND_MASTER_AUDIO = "MASTER_AUDIO"
SONG_MEDIA_KIND_COVER_ART = "COVER_ART"


class SongMediaAsset(Base):
    __tablename__ = "song_media_assets"
    __table_args__ = (
        UniqueConstraint("song_id", "kind", name="uq_song_media_assets_song_kind"),
        CheckConstraint(
            "kind IN ('MASTER_AUDIO', 'COVER_ART')",
            name="ck_song_media_assets_kind",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    song_id = Column(Integer, ForeignKey("songs.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String(32), nullable=False)
    file_path = Column(String(512), nullable=False)
    mime_type = Column(String(128), nullable=False)
    byte_size = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False)
    original_filename = Column(String(512), nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    song = relationship("Song")
