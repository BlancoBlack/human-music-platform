from __future__ import annotations

import re
import unicodedata

import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.models.artist import Artist
from app.models.artist_slug_history import ArtistSlugHistory
from app.models.release import Release
from app.models.release_slug_history import ReleaseSlugHistory
from app.models.song import Song
from app.models.song_slug_history import SongSlugHistory

_NON_ALNUM_RE = re.compile(r"[^a-z0-9\s-]")
_SPACE_HYPHEN_RE = re.compile(r"[\s_-]+")


def slugify_text(raw: str | None) -> str:
    text = (raw or "").strip().lower()
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    cleaned = _NON_ALNUM_RE.sub("", ascii_text)
    compact = _SPACE_HYPHEN_RE.sub("-", cleaned).strip("-")
    return compact or "untitled"


def _allocate_unique_slug_with_connection(
    connection,
    *,
    table_name: str,
    base_slug: str,
) -> str:
    """Allocate unique slug using DB + per-transaction reservations.

    This guarantees slug assignment for insert paths that bypass service helpers.
    """
    reserved = connection.info.setdefault("_reserved_slugs", {})
    table_reserved: set[str] = reserved.setdefault(table_name, set())
    slug = base_slug
    n = 2
    while True:
        if slug in table_reserved:
            slug = f"{base_slug}-{n}"
            n += 1
            continue
        exists = connection.execute(
            sa.text(f"SELECT 1 FROM {table_name} WHERE slug = :slug LIMIT 1"),
            {"slug": slug},
        ).first()
        if exists is None:
            table_reserved.add(slug)
            return slug
        slug = f"{base_slug}-{n}"
        n += 1


@event.listens_for(Artist, "before_insert")
def _artist_before_insert_slug(mapper, connection, target: Artist) -> None:
    current = (target.slug or "").strip()
    if current:
        return
    base_slug = slugify_text(target.name)
    target.slug = _allocate_unique_slug_with_connection(
        connection,
        table_name=Artist.__tablename__,
        base_slug=base_slug,
    )


@event.listens_for(Release, "before_insert")
def _release_before_insert_slug(mapper, connection, target: Release) -> None:
    current = (target.slug or "").strip()
    if current:
        return
    base_slug = slugify_text(target.title)
    target.slug = _allocate_unique_slug_with_connection(
        connection,
        table_name=Release.__tablename__,
        base_slug=base_slug,
    )


@event.listens_for(Song, "before_insert")
def _song_before_insert_slug(mapper, connection, target: Song) -> None:
    current = (target.slug or "").strip()
    if current:
        return
    base_slug = slugify_text(target.title)
    target.slug = _allocate_unique_slug_with_connection(
        connection,
        table_name=Song.__tablename__,
        base_slug=base_slug,
    )


def _allocate_artist_slug(db: Session, base_slug: str) -> str:
    slug = base_slug
    n = 2
    while db.query(Artist.id).filter(Artist.slug == slug).first() is not None:
        slug = f"{base_slug}-{n}"
        n += 1
    return slug


def _allocate_release_slug(db: Session, base_slug: str) -> str:
    slug = base_slug
    n = 2
    while db.query(Release.id).filter(Release.slug == slug).first() is not None:
        slug = f"{base_slug}-{n}"
        n += 1
    return slug


def _allocate_song_slug(db: Session, base_slug: str) -> str:
    slug = base_slug
    n = 2
    while db.query(Song.id).filter(Song.slug == slug).first() is not None:
        slug = f"{base_slug}-{n}"
        n += 1
    return slug


def ensure_artist_slug(db: Session, artist: Artist, *, name_source: str | None = None) -> str:
    existing = (artist.slug or "").strip()
    if existing:
        _ensure_artist_history_current(db, int(artist.id), existing)
        return existing
    base_slug = slugify_text(name_source if name_source is not None else artist.name)
    slug = _allocate_artist_slug(db, base_slug)
    artist.slug = slug
    db.add(artist)
    _set_artist_slug_current(db, int(artist.id), slug)
    return slug


def update_artist_slug(db: Session, artist: Artist, *, name_source: str | None = None) -> str:
    base_slug = slugify_text(name_source if name_source is not None else artist.name)
    current = (artist.slug or "").strip()
    if current == base_slug:
        _ensure_artist_history_current(db, int(artist.id), current)
        return current
    if current:
        taken = db.query(Artist.id).filter(Artist.slug == base_slug, Artist.id != int(artist.id)).first()
    else:
        taken = db.query(Artist.id).filter(Artist.slug == base_slug).first()
    if taken is None:
        new_slug = base_slug
    else:
        new_slug = _allocate_artist_slug(db, base_slug)
    artist.slug = new_slug
    db.add(artist)
    _set_artist_slug_current(db, int(artist.id), new_slug)
    return new_slug


def ensure_release_slug(db: Session, release: Release, *, title_source: str | None = None) -> str:
    existing = (release.slug or "").strip()
    if existing:
        _ensure_release_history_current(db, int(release.id), existing)
        return existing
    base_slug = slugify_text(title_source if title_source is not None else release.title)
    slug = _allocate_release_slug(db, base_slug)
    release.slug = slug
    db.add(release)
    _set_release_slug_current(db, int(release.id), slug)
    return slug


def update_release_slug(db: Session, release: Release, *, title_source: str | None = None) -> str:
    base_slug = slugify_text(title_source if title_source is not None else release.title)
    current = (release.slug or "").strip()
    if current == base_slug:
        _ensure_release_history_current(db, int(release.id), current)
        return current
    if current:
        taken = db.query(Release.id).filter(Release.slug == base_slug, Release.id != int(release.id)).first()
    else:
        taken = db.query(Release.id).filter(Release.slug == base_slug).first()
    if taken is None:
        new_slug = base_slug
    else:
        new_slug = _allocate_release_slug(db, base_slug)
    release.slug = new_slug
    db.add(release)
    _set_release_slug_current(db, int(release.id), new_slug)
    return new_slug


def ensure_song_slug(db: Session, song: Song, *, title_source: str | None = None) -> str:
    existing = (song.slug or "").strip()
    if existing:
        _ensure_song_history_current(db, int(song.id), existing)
        return existing
    base_slug = slugify_text(title_source if title_source is not None else song.title)
    slug = _allocate_song_slug(db, base_slug)
    song.slug = slug
    db.add(song)
    _set_song_slug_current(db, int(song.id), slug)
    return slug


def update_song_slug(db: Session, song: Song, *, title_source: str | None = None) -> str:
    base_slug = slugify_text(title_source if title_source is not None else song.title)
    current = (song.slug or "").strip()
    if current == base_slug:
        _ensure_song_history_current(db, int(song.id), current)
        return current
    if current:
        taken = db.query(Song.id).filter(Song.slug == base_slug, Song.id != int(song.id)).first()
    else:
        taken = db.query(Song.id).filter(Song.slug == base_slug).first()
    if taken is None:
        new_slug = base_slug
    else:
        new_slug = _allocate_song_slug(db, base_slug)
    song.slug = new_slug
    db.add(song)
    _set_song_slug_current(db, int(song.id), new_slug)
    return new_slug


def resolve_artist_slug(db: Session, slug: str) -> tuple[Artist | None, bool]:
    artist = db.query(Artist).filter(Artist.slug == slug).first()
    if artist is not None:
        return artist, True
    hist = db.query(ArtistSlugHistory).filter(ArtistSlugHistory.slug == slug).first()
    if hist is None:
        return None, False
    artist = db.query(Artist).filter(Artist.id == int(hist.artist_id)).first()
    return artist, False if artist is not None else False


def resolve_release_slug(db: Session, slug: str) -> tuple[Release | None, bool]:
    release = db.query(Release).filter(Release.slug == slug).first()
    if release is not None:
        return release, True
    hist = db.query(ReleaseSlugHistory).filter(ReleaseSlugHistory.slug == slug).first()
    if hist is None:
        return None, False
    release = db.query(Release).filter(Release.id == int(hist.release_id)).first()
    return release, False if release is not None else False


def resolve_song_slug(db: Session, slug: str) -> tuple[Song | None, bool]:
    song = db.query(Song).filter(Song.slug == slug, Song.deleted_at.is_(None)).first()
    if song is not None:
        return song, True
    hist = db.query(SongSlugHistory).filter(SongSlugHistory.slug == slug).first()
    if hist is None:
        return None, False
    song = db.query(Song).filter(Song.id == int(hist.song_id), Song.deleted_at.is_(None)).first()
    return song, False if song is not None else False


def _set_artist_slug_current(db: Session, artist_id: int, slug: str) -> None:
    db.query(ArtistSlugHistory).filter(ArtistSlugHistory.artist_id == int(artist_id)).update(
        {"is_current": False},
        synchronize_session=False,
    )
    row = db.query(ArtistSlugHistory).filter(ArtistSlugHistory.slug == slug).first()
    if row is None:
        row = ArtistSlugHistory(artist_id=int(artist_id), slug=slug, is_current=True)
    else:
        row.artist_id = int(artist_id)
        row.is_current = True
    db.add(row)


def _set_release_slug_current(db: Session, release_id: int, slug: str) -> None:
    db.query(ReleaseSlugHistory).filter(ReleaseSlugHistory.release_id == int(release_id)).update(
        {"is_current": False},
        synchronize_session=False,
    )
    row = db.query(ReleaseSlugHistory).filter(ReleaseSlugHistory.slug == slug).first()
    if row is None:
        row = ReleaseSlugHistory(release_id=int(release_id), slug=slug, is_current=True)
    else:
        row.release_id = int(release_id)
        row.is_current = True
    db.add(row)


def _set_song_slug_current(db: Session, song_id: int, slug: str) -> None:
    db.query(SongSlugHistory).filter(SongSlugHistory.song_id == int(song_id)).update(
        {"is_current": False},
        synchronize_session=False,
    )
    row = db.query(SongSlugHistory).filter(SongSlugHistory.slug == slug).first()
    if row is None:
        row = SongSlugHistory(song_id=int(song_id), slug=slug, is_current=True)
    else:
        row.song_id = int(song_id)
        row.is_current = True
    db.add(row)


def _ensure_artist_history_current(db: Session, artist_id: int, slug: str) -> None:
    row = db.query(ArtistSlugHistory).filter(ArtistSlugHistory.slug == slug).first()
    if row is None or int(row.artist_id) != int(artist_id) or not bool(row.is_current):
        _set_artist_slug_current(db, int(artist_id), slug)


def _ensure_release_history_current(db: Session, release_id: int, slug: str) -> None:
    row = db.query(ReleaseSlugHistory).filter(ReleaseSlugHistory.slug == slug).first()
    if row is None or int(row.release_id) != int(release_id) or not bool(row.is_current):
        _set_release_slug_current(db, int(release_id), slug)


def _ensure_song_history_current(db: Session, song_id: int, slug: str) -> None:
    row = db.query(SongSlugHistory).filter(SongSlugHistory.slug == slug).first()
    if row is None or int(row.song_id) != int(song_id) or not bool(row.is_current):
        _set_song_slug_current(db, int(song_id), slug)
