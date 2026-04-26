from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.artist import Artist
from app.models.release import Release


@dataclass(frozen=True)
class ReleaseTemplate:
    key: str
    title_suffix: str
    release_type: str
    release_date: datetime
    state: str


def upsert_artist_releases(
    db: Session,
    *,
    artist: Artist,
    templates: list[ReleaseTemplate],
) -> dict[str, Release]:
    out: dict[str, Release] = {}
    for template in templates:
        row = (
            db.query(Release)
            .filter(Release.artist_id == int(artist.id), Release.title == f"{artist.name} — {template.title_suffix}")
            .one_or_none()
        )
        if row is None:
            row = Release(
                title=f"{artist.name} — {template.title_suffix}",
                artist_id=int(artist.id),
                type=template.release_type,
                release_date=template.release_date,
                discoverable_at=template.release_date,
                state=template.state,
            )
            db.add(row)
        else:
            row.title = f"{artist.name} — {template.title_suffix}"
            row.type = template.release_type
            row.release_date = template.release_date
            row.discoverable_at = template.release_date
            row.state = template.state
        db.flush()
        out[template.key] = row
    return out
