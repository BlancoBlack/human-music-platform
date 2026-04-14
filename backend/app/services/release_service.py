from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.artist import Artist
from app.models.release import (
    RELEASE_STATE_PUBLISHED,
    RELEASE_STATE_SCHEDULED,
    RELEASE_STATE_DRAFT,
    RELEASE_TYPE_ALBUM,
    RELEASE_TYPE_SINGLE,
    Release,
)
from app.models.release_media_asset import (
    RELEASE_MEDIA_ASSET_TYPE_COVER_ART,
    ReleaseMediaAsset,
)
from app.models.song import SONG_STATE_READY_FOR_RELEASE
from app.models.song import Song
from app.models.song_media_asset import (
    SONG_MEDIA_KIND_COVER_ART,
    SONG_MEDIA_KIND_MASTER_AUDIO,
    SongMediaAsset,
)

logger = logging.getLogger(__name__)

_ALLOCATION_MAX_ATTEMPTS = 3


def _log_release_bind_blocked(
    *,
    reason: str,
    song_id: int,
    source_release_id: int | None,
    target_release_id: int,
) -> None:
    logger.warning(
        "release_reassignment_blocked",
        extra={
            "reason": reason,
            "song_id": int(song_id),
            "source_release_id": source_release_id,
            "target_release_id": int(target_release_id),
        },
    )


def _allocate_next_track_number(db: Session, release_id: int) -> int:
    """
    Next ``track_number`` for a release (1-based), serialized on Postgres via
    ``SELECT FOR UPDATE`` on the parent ``releases`` row.
    """
    rid = int(release_id)
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        db.query(Release).filter(Release.id == rid).with_for_update().one()

    max_track = (
        db.query(func.coalesce(func.max(Song.track_number), 0))
        .filter(Song.release_id == rid)
        .scalar()
    )
    return int(max_track or 0) + 1


# -----------------------------------------------------------------------------
# Release auto-publish scheduler (MVP polling)
# -----------------------------------------------------------------------------
# Purpose:
# - Transition releases from "scheduled" -> "published" when
#   ``now >= discoverable_at`` so discovery visibility can rely on:
#       release.state == "published" AND now >= discoverable_at
#
# Why polling:
# - MVP implementation uses a lightweight in-process polling loop from worker.py.
# - This replaced the temporary behavior where "scheduled" releases were treated
#   as visible by discovery.
#
# Guarantees:
# - Deterministic transition condition based on DB state/time comparison.
# - Idempotent updates by filtering strictly on state == "scheduled".
#
# Limitations:
# - Publish latency up to polling interval.
# - Not event-driven.
# - Not horizontally scalable without distributed coordination/locking.
# -----------------------------------------------------------------------------


def create_release(
    db: Session,
    *,
    title: str,
    artist_id: int,
    release_type: str,
    release_date: datetime,
    discoverable_at: datetime | None = None,
) -> Release:
    cleaned_title = (title or "").strip()
    if not cleaned_title:
        raise ValueError("title is required.")
    rtype = str(release_type or "").strip().lower()
    if rtype not in {RELEASE_TYPE_SINGLE, RELEASE_TYPE_ALBUM}:
        raise ValueError("release_type must be 'single' or 'album'.")
    if db.query(Artist.id).filter(Artist.id == int(artist_id)).first() is None:
        raise ValueError(f"Artist {artist_id} not found.")

    release = Release(
        title=cleaned_title,
        artist_id=int(artist_id),
        type=rtype,
        release_date=release_date,
        discoverable_at=discoverable_at,
        state=RELEASE_STATE_DRAFT,
    )
    db.add(release)
    db.commit()
    db.refresh(release)
    return release


def get_release_tracks(db: Session, release_id: int) -> list[dict]:
    release = db.query(Release).filter(Release.id == int(release_id)).first()
    if release is None:
        raise ValueError(f"Release {release_id} not found.")

    album_cover_ok = release.type == RELEASE_TYPE_ALBUM and (
        db.query(ReleaseMediaAsset.id)
        .filter(
            ReleaseMediaAsset.release_id == int(release_id),
            ReleaseMediaAsset.asset_type == RELEASE_MEDIA_ASSET_TYPE_COVER_ART,
        )
        .first()
        is not None
    )

    songs = (
        db.query(Song)
        .filter(Song.release_id == int(release_id), Song.deleted_at.is_(None))
        .order_by(
            Song.track_number.is_(None).asc(),
            Song.track_number.asc(),
            Song.id.asc(),
        )
        .all()
    )
    if not songs:
        return []

    song_ids = [int(s.id) for s in songs]
    asset_rows = (
        db.query(SongMediaAsset.song_id, SongMediaAsset.kind)
        .filter(
            SongMediaAsset.song_id.in_(song_ids),
            SongMediaAsset.kind.in_([SONG_MEDIA_KIND_MASTER_AUDIO, SONG_MEDIA_KIND_COVER_ART]),
        )
        .all()
    )

    master_ids: set[int] = set()
    cover_ids: set[int] = set()
    for sid, kind in asset_rows:
        sid_i = int(sid)
        if kind == SONG_MEDIA_KIND_MASTER_AUDIO:
            master_ids.add(sid_i)
        elif kind == SONG_MEDIA_KIND_COVER_ART:
            cover_ids.add(sid_i)

    tracks: list[dict] = []
    for song in songs:
        state = str(song.state or "").strip()
        if state == SONG_STATE_READY_FOR_RELEASE:
            completion_status = "complete"
        elif state == "draft":
            completion_status = "empty"
        else:
            completion_status = "incomplete"

        sid = int(song.id)
        if release.type == RELEASE_TYPE_ALBUM:
            has_cover_art = bool(album_cover_ok)
        else:
            has_cover_art = sid in cover_ids
        tracks.append(
            {
                "id": sid,
                "title": song.title,
                "track_number": song.track_number,
                "state": song.state,
                "upload_status": song.upload_status,
                "has_master_audio": sid in master_ids,
                "has_cover_art": has_cover_art,
                "completion_status": completion_status,
            }
        )
    return tracks


def get_release_progress(db: Session, release_id: int) -> dict:
    tracks = get_release_tracks(db, int(release_id))
    total_tracks = len(tracks)
    completed_tracks = sum(1 for t in tracks if t["completion_status"] == "complete")
    empty_tracks = sum(1 for t in tracks if t["completion_status"] == "empty")
    incomplete_tracks = total_tracks - completed_tracks - empty_tracks
    return {
        "total_tracks": int(total_tracks),
        "completed_tracks": int(completed_tracks),
        "incomplete_tracks": int(incomplete_tracks),
        "empty_tracks": int(empty_tracks),
    }


def normalize_release_track_order(db: Session, release_id: int) -> int:
    """
    Maintenance utility (not auto-invoked): compact ``track_number`` to ``1..N``
    for a release in deterministic order. Caller must ``commit``.

    Returns the number of songs whose ``track_number`` was updated.
    """
    rid = int(release_id)
    songs = (
        db.query(Song)
        .filter(Song.release_id == rid, Song.deleted_at.is_(None))
        .order_by(Song.track_number.is_(None).asc(), Song.track_number.asc(), Song.id.asc())
        .all()
    )
    updated = 0
    for i, row in enumerate(songs, start=1):
        if row.track_number != i:
            row.track_number = i
            db.add(row)
            updated += 1
    if updated:
        db.flush()
    return int(updated)


def bind_song_to_release(db: Session, *, song: Song, release_id: int) -> None:
    """
    Attach ``song`` to ``release_id`` with strict immutability rules and
    race-safe ``track_number`` allocation.

    Allocation + ``flush`` run inside a SAVEPOINT (``Session.begin_nested``).
    On ``IntegrityError``, only that savepoint rolls back — not the whole
    session — so unrelated pending work in the outer transaction is preserved.
    Retry logic applies only to that allocation scope (max
    ``_ALLOCATION_MAX_ATTEMPTS``).
    """
    song_id = int(song.id)
    target_rid = int(release_id)

    s = db.query(Song).filter(Song.id == song_id, Song.deleted_at.is_(None)).first()
    if s is None:
        raise ValueError(f"Song {song_id} not found.")

    release = db.query(Release).filter(Release.id == target_rid).first()
    if release is None:
        raise ValueError(f"Release {target_rid} not found.")

    if int(s.artist_id) != int(release.artist_id):
        raise ValueError(
            f"Song {s.id} artist_id={s.artist_id} does not match "
            f"release {target_rid} artist_id={release.artist_id}."
        )

    if release.state != RELEASE_STATE_DRAFT:
        _log_release_bind_blocked(
            reason="target_release_not_draft",
            song_id=song_id,
            source_release_id=int(s.release_id) if s.release_id is not None else None,
            target_release_id=target_rid,
        )
        raise ValueError(
            f"Release {target_rid} is {release.state!r}; songs may only be bound while release is draft."
        )

    prev_rid = int(s.release_id) if s.release_id is not None else None
    changing_release = prev_rid is None or prev_rid != target_rid

    if changing_release:
        if s.state == SONG_STATE_READY_FOR_RELEASE:
            _log_release_bind_blocked(
                reason="song_ready_for_release",
                song_id=song_id,
                source_release_id=prev_rid,
                target_release_id=target_rid,
            )
            raise ValueError(
                f"Song {song_id} is {SONG_STATE_READY_FOR_RELEASE!r}; release membership cannot change."
            )
        if prev_rid is not None:
            source_release = db.query(Release).filter(Release.id == int(prev_rid)).first()
            if source_release is not None and source_release.state != RELEASE_STATE_DRAFT:
                _log_release_bind_blocked(
                    reason="source_release_not_draft",
                    song_id=song_id,
                    source_release_id=prev_rid,
                    target_release_id=target_rid,
                )
                raise ValueError(
                    f"Song {song_id} belongs to release {prev_rid} in state "
                    f"{source_release.state!r}; reassignment is not allowed."
                )

    allocated_for_log: int | None = None

    if s.track_number is None:
        for attempt in range(1, _ALLOCATION_MAX_ATTEMPTS + 1):
            allocated_this_attempt: int | None = None
            try:
                with db.begin_nested():
                    s2 = (
                        db.query(Song)
                        .filter(Song.id == song_id, Song.deleted_at.is_(None))
                        .one()
                    )
                    if s2.track_number is not None:
                        s2.release_id = target_rid
                        db.add(s2)
                        db.flush()
                    else:
                        next_n = _allocate_next_track_number(db, target_rid)
                        s2.track_number = int(next_n)
                        s2.release_id = target_rid
                        db.add(s2)
                        db.flush()
                        allocated_this_attempt = int(next_n)
            except IntegrityError as exc:
                if attempt >= _ALLOCATION_MAX_ATTEMPTS:
                    raise ValueError(
                        f"Could not allocate a unique track_number for song {song_id} on release {target_rid}."
                    ) from exc
                logger.info(
                    "track_number_retry",
                    extra={
                        "attempt": int(attempt),
                        "release_id": target_rid,
                        "song_id": song_id,
                    },
                )
                continue
            allocated_for_log = allocated_this_attempt
            break
        if allocated_for_log is not None:
            logger.info(
                "track_number_allocated",
                extra={
                    "release_id": target_rid,
                    "song_id": song_id,
                    "track_number": int(allocated_for_log),
                },
            )
    else:
        s.release_id = target_rid
        db.add(s)
        db.flush()


def attach_song_to_release(db: Session, *, song_id: int, release_id: int) -> Song:
    song = (
        db.query(Song)
        .filter(Song.id == int(song_id), Song.deleted_at.is_(None))
        .first()
    )
    if song is None:
        raise ValueError(f"Song {song_id} not found.")
    bind_song_to_release(db, song=song, release_id=int(release_id))
    db.commit()
    db.refresh(song)
    return song


def validate_release_publishable(db: Session, *, release_id: int) -> tuple[bool, list[str]]:
    errors: list[str] = []
    release = db.query(Release).filter(Release.id == int(release_id)).first()
    if release is None:
        return False, [f"Release {release_id} not found."]

    songs = (
        db.query(Song)
        .filter(Song.release_id == int(release_id), Song.deleted_at.is_(None))
        .all()
    )
    if not songs:
        errors.append("Release must contain at least one song.")

    for song in songs:
        if int(song.artist_id or 0) != int(release.artist_id):
            errors.append(
                f"Song {song.id} artist_id={song.artist_id} does not match release artist_id={release.artist_id}."
            )
        if song.state != SONG_STATE_READY_FOR_RELEASE:
            errors.append(
                f"Song {song.id} state={song.state!r} is not {SONG_STATE_READY_FOR_RELEASE!r}."
            )

    if release.type == RELEASE_TYPE_SINGLE and len(songs) != 1:
        errors.append("Single release must contain exactly 1 song.")
    if release.type == RELEASE_TYPE_ALBUM and len(songs) < 2:
        errors.append("Album release must contain at least 2 songs.")

    if release.type == RELEASE_TYPE_ALBUM:
        if (
            db.query(ReleaseMediaAsset.id)
            .filter(
                ReleaseMediaAsset.release_id == int(release_id),
                ReleaseMediaAsset.asset_type == RELEASE_MEDIA_ASSET_TYPE_COVER_ART,
            )
            .first()
            is None
        ):
            errors.append(
                "Album release requires release-level cover art (ReleaseMediaAsset COVER_ART)."
            )

    if release.release_date is None:
        errors.append("release_date is required.")

    return len(errors) == 0, errors


def is_release_discoverable(release: Release, now: datetime | None = None) -> bool:
    current = now or datetime.now(UTC)
    if release.state != RELEASE_STATE_PUBLISHED:
        return False
    if release.discoverable_at is None:
        return False
    discoverable_at = (
        release.discoverable_at.replace(tzinfo=UTC)
        if release.discoverable_at.tzinfo is None
        else release.discoverable_at
    )
    return current >= discoverable_at


def is_song_discoverable(song: Song, now: datetime | None = None) -> bool:
    """
    Backward-compatible visibility contract:
    - legacy songs (no release): keep upload_status=ready behavior
    - release-linked songs: follow release lifecycle visibility
    """
    if song.deleted_at is not None:
        return False
    if song.release_id is None:
        return (song.upload_status or "").strip().lower() == "ready"
    if song.release is None:
        return False
    return is_release_discoverable(song.release, now=now)


def publish_release(db: Session, *, release_id: int) -> Release:
    logger.info("release_publish_attempt", extra={"release_id": int(release_id)})
    release = db.query(Release).filter(Release.id == int(release_id)).first()
    if release is None:
        logger.error("release_publish_failed", extra={"release_id": int(release_id), "errors": ["release not found"]})
        raise ValueError(f"Release {release_id} not found.")

    is_valid, errors = validate_release_publishable(db, release_id=int(release_id))
    if not is_valid:
        logger.error(
            "release_publish_failed",
            extra={"release_id": int(release_id), "errors": errors},
        )
        raise ValueError("Release is not publishable: " + " | ".join(errors))

    now = datetime.now(UTC)
    discoverable_at = release.release_date or now
    if discoverable_at.tzinfo is None:
        discoverable_at = discoverable_at.replace(tzinfo=UTC)

    release.discoverable_at = discoverable_at
    if discoverable_at > now:
        release.state = RELEASE_STATE_SCHEDULED
    else:
        release.state = RELEASE_STATE_PUBLISHED

    db.add(release)
    db.commit()
    db.refresh(release)
    logger.info(
        "release_publish_success",
        extra={
            "release_id": int(release_id),
            "state": release.state,
            "discoverable_at": release.discoverable_at.isoformat() if release.discoverable_at else None,
        },
    )
    return release


def publish_due_releases(db: Session) -> int:
    """
    Auto-transition due releases: scheduled -> published when discoverable_at <= now.

    Idempotent by design because we only target rows in scheduled state.
    """
    now = datetime.now(UTC)
    due = (
        db.query(Release)
        .filter(
            Release.state == RELEASE_STATE_SCHEDULED,
            Release.discoverable_at.isnot(None),
            Release.discoverable_at <= now,
        )
        .all()
    )
    count = 0
    for release in due:
        release.state = RELEASE_STATE_PUBLISHED
        db.add(release)
        count += 1
        logger.info(
            "release_auto_published",
            extra={
                "release_id": int(release.id),
                "at": now.isoformat(),
            },
        )
    if count > 0:
        db.commit()
    logger.info(
        "release_auto_publish_poll",
        extra={
            "processed_count": int(count),
            "at": now.isoformat(),
        },
    )
    return count


def create_single_release_for_song(
    db: Session,
    *,
    song: Song,
    release_date: datetime | None = None,
) -> Release:
    """
    Create a default SINGLE release for a song and attach it.
    Keeps upload UX unchanged while making new songs release-aware.
    """
    if song.release_id is not None and int(song.release_id) > 0:
        release = db.query(Release).filter(Release.id == int(song.release_id)).first()
        if release is not None:
            return release

    when = release_date or datetime.utcnow()
    release = Release(
        title=(song.title or "").strip() or f"Song {int(song.id)}",
        artist_id=int(song.artist_id),
        type=RELEASE_TYPE_SINGLE,
        release_date=when,
        state=RELEASE_STATE_DRAFT,
    )
    db.add(release)
    db.flush()

    bind_song_to_release(db, song=song, release_id=int(release.id))
    db.refresh(song)
    logger.info(
        "release_created_for_song",
        extra={
            "song_id": int(song.id),
            "release_id": int(release.id),
            "artist_id": int(song.artist_id),
            "release_type": RELEASE_TYPE_SINGLE,
        },
    )
    return release
