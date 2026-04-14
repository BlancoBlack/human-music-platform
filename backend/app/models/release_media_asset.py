from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import relationship

from app.core.database import Base

RELEASE_MEDIA_ASSET_TYPE_COVER_ART = "COVER_ART"
RELEASE_MEDIA_ASSET_TYPE_VALUES = (RELEASE_MEDIA_ASSET_TYPE_COVER_ART,)


class ReleaseMediaAsset(Base):
    __tablename__ = "release_media_assets"
    __table_args__ = (
        UniqueConstraint("release_id", "asset_type", name="uq_release_media_assets_release_asset"),
        CheckConstraint(
            "asset_type IN ('COVER_ART')",
            name="ck_release_media_assets_asset_type",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    release_id = Column(Integer, ForeignKey("releases.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_type = Column(String(32), nullable=False)
    file_path = Column(String(512), nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    release = relationship("Release", back_populates="media_assets")
