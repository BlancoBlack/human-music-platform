from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.release import Release
from app.models.release_media_asset import (
    RELEASE_MEDIA_ASSET_TYPE_COVER_ART,
    ReleaseMediaAsset,
)
from app.models.song import Song


def _release_cover_path(db: Session, release_id: int) -> str | None:
    row = (
        db.query(ReleaseMediaAsset.file_path)
        .filter(
            ReleaseMediaAsset.release_id == int(release_id),
            ReleaseMediaAsset.asset_type == RELEASE_MEDIA_ASSET_TYPE_COVER_ART,
        )
        .first()
    )
    if row is None:
        return None
    value = row[0]
    if value is None:
        return None
    path = str(value).strip()
    return path or None


def effective_song_cover(db: Session, song: Song) -> str | None:
    """
    Compatibility resolver for song artwork during cover ownership transition.

    Rules:
    - If song has release_id, resolve from release cover only.
    - If song has no release_id, return None (strict release-owned artwork model).
    - If no release cover exists, return None.
    """
    release_id = getattr(song, "release_id", None)
    if release_id is not None:
        # Ensure release exists before attempting release-cover lookup.
        release_exists = (
            db.query(Release.id).filter(Release.id == int(release_id)).first()
            is not None
        )
        if not release_exists:
            return None
        return _release_cover_path(db, int(release_id))

    return None
