from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.release import Release
from app.models.release_participant import (
    RELEASE_PARTICIPANT_APPROVAL_TYPE_FEATURE,
    RELEASE_PARTICIPANT_APPROVAL_TYPE_NONE,
    RELEASE_PARTICIPANT_APPROVAL_TYPE_SPLIT,
    RELEASE_PARTICIPANT_ROLE_COLLABORATOR,
    RELEASE_PARTICIPANT_ROLE_FEATURED,
    RELEASE_PARTICIPANT_ROLE_PRIMARY,
    RELEASE_PARTICIPANT_STATUS_ACCEPTED,
    RELEASE_PARTICIPANT_STATUS_PENDING,
    ReleaseParticipant,
)
from app.models.artist import Artist
from app.models.song import Song
from app.models.song_artist_split import SongArtistSplit
from app.models.song_featured_artist import SongFeaturedArtist
from app.services.release_approval_service import refresh_release_approval_status


def invalidate_stale_split_approvals(
    db: Session,
    *,
    release_id: int,
    commit: bool = False,
) -> int:
    release = db.query(Release).filter(Release.id == int(release_id)).first()
    if release is None:
        raise ValueError(f"Release {release_id} not found.")
    current_split_version = int(release.split_version or 1)
    rows = (
        db.query(ReleaseParticipant)
        .filter(
            ReleaseParticipant.release_id == int(release_id),
            ReleaseParticipant.approval_type == RELEASE_PARTICIPANT_APPROVAL_TYPE_SPLIT,
            ReleaseParticipant.status == RELEASE_PARTICIPANT_STATUS_ACCEPTED,
        )
        .all()
    )
    invalidated = 0
    for row in rows:
        approved_version = row.approved_split_version
        if approved_version is not None and int(approved_version) == current_split_version:
            continue
        row.status = RELEASE_PARTICIPANT_STATUS_PENDING
        row.approved_at = None
        row.approved_split_version = None
        row.rejection_reason = None
        db.add(row)
        invalidated += 1

    refresh_release_approval_status(db, release_id=int(release_id))
    if commit:
        db.commit()
    else:
        db.flush()
    return invalidated


def _upsert_candidate(
    candidates: dict[int, dict[str, str | bool]],
    *,
    artist_id: int,
    role: str,
    status: str,
) -> None:
    existing = candidates.get(int(artist_id))
    default_approval_type = (
        RELEASE_PARTICIPANT_APPROVAL_TYPE_FEATURE
        if str(role) == RELEASE_PARTICIPANT_ROLE_FEATURED
        else RELEASE_PARTICIPANT_APPROVAL_TYPE_SPLIT
    )
    if existing is None:
        candidates[int(artist_id)] = {
            "role": str(role),
            "status": str(status),
            "requires_approval": bool(status != RELEASE_PARTICIPANT_STATUS_ACCEPTED),
            "approval_type": default_approval_type,
        }
        return

    rank = {
        RELEASE_PARTICIPANT_ROLE_FEATURED: 1,
        RELEASE_PARTICIPANT_ROLE_COLLABORATOR: 2,
        RELEASE_PARTICIPANT_ROLE_PRIMARY: 3,
    }
    if rank.get(role, 0) > rank.get(existing["role"], 0):
        existing["role"] = role
    if status == RELEASE_PARTICIPANT_STATUS_ACCEPTED:
        existing["status"] = RELEASE_PARTICIPANT_STATUS_ACCEPTED


def _upsert_approval_defaults(
    candidates: dict[int, dict[str, str | bool]],
    *,
    artist_id: int,
    requires_approval: bool,
    approval_type: str,
) -> None:
    existing = candidates.get(int(artist_id))
    if existing is None:
        return
    if not bool(existing.get("requires_approval", True)):
        return
    current_approval_type = str(existing.get("approval_type", RELEASE_PARTICIPANT_APPROVAL_TYPE_SPLIT))
    next_approval_type = str(approval_type)
    if (
        current_approval_type == RELEASE_PARTICIPANT_APPROVAL_TYPE_SPLIT
        and next_approval_type == RELEASE_PARTICIPANT_APPROVAL_TYPE_FEATURE
    ):
        return
    existing["requires_approval"] = bool(requires_approval)
    existing["approval_type"] = next_approval_type


def _resolve_owner_artist_id(db: Session, release: Release) -> int | None:
    owner_user_id = getattr(release, "owner_user_id", None)
    if owner_user_id is None:
        return None
    owner_artist_row = (
        db.query(Artist.id)
        .filter(Artist.owner_user_id == int(owner_user_id))
        .order_by(Artist.id.asc())
        .first()
    )
    if owner_artist_row is None:
        return None
    return int(owner_artist_row[0])


def _build_release_participant_snapshot(
    db: Session,
    release: Release,
) -> tuple[dict[int, dict[str, str | bool]], int | None, set[int]]:
    release_id = int(release.id)
    owner_artist_id = _resolve_owner_artist_id(db, release)
    candidates: dict[int, dict[str, str | bool]] = {}
    featured_artist_ids: set[int] = set()

    _upsert_candidate(
        candidates,
        artist_id=int(release.artist_id),
        role=RELEASE_PARTICIPANT_ROLE_PRIMARY,
        status=(
            RELEASE_PARTICIPANT_STATUS_ACCEPTED
            if owner_artist_id is not None and int(release.artist_id) == int(owner_artist_id)
            else RELEASE_PARTICIPANT_STATUS_PENDING
        ),
    )

    songs = (
        db.query(Song.id, Song.artist_id)
        .filter(Song.release_id == release_id, Song.deleted_at.is_(None))
        .all()
    )
    song_ids: list[int] = []
    for song_id, song_primary_artist_id in songs:
        song_ids.append(int(song_id))
        primary_id = int(song_primary_artist_id)
        _upsert_candidate(
            candidates,
            artist_id=primary_id,
            role=RELEASE_PARTICIPANT_ROLE_PRIMARY,
            status=RELEASE_PARTICIPANT_STATUS_PENDING,
        )

    if owner_artist_id is not None:
        _upsert_candidate(
            candidates,
            artist_id=int(owner_artist_id),
            role=RELEASE_PARTICIPANT_ROLE_COLLABORATOR,
            status=RELEASE_PARTICIPANT_STATUS_ACCEPTED,
        )
    if not song_ids:
        return candidates, owner_artist_id, featured_artist_ids

    split_rows = (
        db.query(SongArtistSplit.artist_id)
        .filter(SongArtistSplit.song_id.in_(song_ids))
        .distinct()
        .all()
    )
    for (artist_id,) in split_rows:
        split_artist_id = int(artist_id)
        _upsert_candidate(
            candidates,
            artist_id=split_artist_id,
            role=RELEASE_PARTICIPANT_ROLE_COLLABORATOR,
            status=RELEASE_PARTICIPANT_STATUS_PENDING,
        )
        _upsert_approval_defaults(
            candidates,
            artist_id=split_artist_id,
            requires_approval=True,
            approval_type=RELEASE_PARTICIPANT_APPROVAL_TYPE_SPLIT,
        )

    featured_rows = (
        db.query(SongFeaturedArtist.artist_id)
        .filter(SongFeaturedArtist.song_id.in_(song_ids))
        .distinct()
        .all()
    )
    for (artist_id,) in featured_rows:
        featured_artist_ids.add(int(artist_id))
        _upsert_candidate(
            candidates,
            artist_id=int(artist_id),
            role=RELEASE_PARTICIPANT_ROLE_FEATURED,
            status=RELEASE_PARTICIPANT_STATUS_PENDING,
        )
        _upsert_approval_defaults(
            candidates,
            artist_id=int(artist_id),
            requires_approval=True,
            approval_type=RELEASE_PARTICIPANT_APPROVAL_TYPE_FEATURE,
        )

    return candidates, owner_artist_id, featured_artist_ids


def get_release_feature_artist_ids(db: Session, *, release_id: int) -> set[int]:
    song_ids = [
        int(row[0])
        for row in db.query(Song.id)
        .filter(Song.release_id == int(release_id), Song.deleted_at.is_(None))
        .all()
    ]
    if not song_ids:
        return set()
    return {
        int(row[0])
        for row in db.query(SongFeaturedArtist.artist_id)
        .filter(SongFeaturedArtist.song_id.in_(song_ids))
        .distinct()
        .all()
    }


def get_release_feature_artist_ids_map(db: Session, *, release_ids: list[int]) -> dict[int, set[int]]:
    mapping: dict[int, set[int]] = {int(rid): set() for rid in release_ids}
    if not release_ids:
        return mapping
    rows = (
        db.query(Song.release_id, SongFeaturedArtist.artist_id)
        .join(SongFeaturedArtist, SongFeaturedArtist.song_id == Song.id)
        .filter(Song.release_id.in_(release_ids), Song.deleted_at.is_(None))
        .distinct()
        .all()
    )
    for release_id, artist_id in rows:
        mapping[int(release_id)].add(int(artist_id))
    return mapping


def sync_release_participants(db: Session, release_id: int, *, commit: bool = False) -> list[ReleaseParticipant]:
    """
    Recompute release participants from current release-song metadata.

    Rules:
    - owner artist (if resolvable from owner_user_id) is always accepted
    - song primary artists map to primary
    - split-only artists map to collaborator
    - featured-only artists map to featured
    - existing statuses/approved_at are preserved for existing participants
    """
    release = db.query(Release).filter(Release.id == int(release_id)).first()
    if release is None:
        raise ValueError(f"Release {release_id} not found.")

    desired, owner_artist_id, featured_artist_ids = _build_release_participant_snapshot(db, release)
    existing_rows = (
        db.query(ReleaseParticipant)
        .filter(ReleaseParticipant.release_id == int(release_id))
        .all()
    )
    by_artist = {int(row.artist_id): row for row in existing_rows}

    desired_artist_ids = set(desired.keys())
    existing_artist_ids = set(by_artist.keys())

    for artist_id in existing_artist_ids - desired_artist_ids:
        db.delete(by_artist[artist_id])

    for artist_id, values in desired.items():
        current = by_artist.get(int(artist_id))
        if current is None:
            db.add(
                ReleaseParticipant(
                    release_id=int(release_id),
                    artist_id=int(artist_id),
                    role=str(values["role"]),
                    status=str(values["status"]),
                    requires_approval=bool(values.get("requires_approval", True)),
                    approval_type=str(values.get("approval_type", RELEASE_PARTICIPANT_APPROVAL_TYPE_SPLIT)),
                )
            )
            continue
        if current.role != values["role"]:
            current.role = values["role"]
            db.add(current)
        desired_approval_type = str(values.get("approval_type", RELEASE_PARTICIPANT_APPROVAL_TYPE_SPLIT))
        if (
            desired_approval_type == RELEASE_PARTICIPANT_APPROVAL_TYPE_SPLIT
            and current.approval_type != RELEASE_PARTICIPANT_APPROVAL_TYPE_SPLIT
        ):
            current.approval_type = RELEASE_PARTICIPANT_APPROVAL_TYPE_SPLIT
            current.requires_approval = True
            db.add(current)

        # Preserve existing approval fields for existing rows.
        # Owner is the only force-update exception.
        if (
            owner_artist_id is not None
            and int(artist_id) == int(owner_artist_id)
        ):
            changed = False
            if current.status != RELEASE_PARTICIPANT_STATUS_ACCEPTED:
                current.status = RELEASE_PARTICIPANT_STATUS_ACCEPTED
                changed = True
            if current.requires_approval:
                current.requires_approval = False
                changed = True
            if current.approval_type != RELEASE_PARTICIPANT_APPROVAL_TYPE_NONE:
                current.approval_type = RELEASE_PARTICIPANT_APPROVAL_TYPE_NONE
                changed = True
            if current.approved_split_version is not None:
                current.approved_split_version = None
                changed = True
            if changed:
                db.add(current)
        continue

    # Apply approval defaults only for newly inserted participants, then
    # enforce owner invariants.
    db.flush()
    if owner_artist_id is not None:
        owner_row = (
            db.query(ReleaseParticipant)
            .filter(
                ReleaseParticipant.release_id == int(release_id),
                ReleaseParticipant.artist_id == int(owner_artist_id),
            )
            .first()
        )
        if owner_row is not None:
            changed = False
            if owner_row.status != RELEASE_PARTICIPANT_STATUS_ACCEPTED:
                owner_row.status = RELEASE_PARTICIPANT_STATUS_ACCEPTED
                changed = True
            if owner_row.requires_approval:
                owner_row.requires_approval = False
                changed = True
            if owner_row.approval_type != RELEASE_PARTICIPANT_APPROVAL_TYPE_NONE:
                owner_row.approval_type = RELEASE_PARTICIPANT_APPROVAL_TYPE_NONE
                changed = True
            if owner_row.approved_split_version is not None:
                owner_row.approved_split_version = None
                changed = True
            if changed:
                db.add(owner_row)

    invalidate_stale_split_approvals(db, release_id=int(release_id), commit=False)
    refresh_release_approval_status(db, release_id=int(release_id))

    if commit:
        db.commit()
    else:
        db.flush()

    participants = (
        db.query(ReleaseParticipant)
        .filter(ReleaseParticipant.release_id == int(release_id))
        .order_by(ReleaseParticipant.id.asc())
        .all()
    )
    # keep this context DB-derived and stable (independent of participant status)
    for row in participants:
        setattr(row, "has_feature_context", int(row.artist_id) in featured_artist_ids)
    return participants
