from __future__ import annotations

from datetime import datetime, UTC

from sqlalchemy.orm import Session

from app.models.artist import Artist
from app.models.release import (
    RELEASE_APPROVAL_STATUS_PENDING,
    RELEASE_APPROVAL_STATUS_READY,
    Release,
)
from app.models.release_participant import (
    RELEASE_PARTICIPANT_APPROVAL_TYPE_SPLIT,
    RELEASE_PARTICIPANT_STATUS_ACCEPTED,
    RELEASE_PARTICIPANT_STATUS_REJECTED,
    ReleaseParticipant,
)
from app.models.user import User


def _assert_user_owns_artist_or_403(db: Session, *, user: User, artist_id: int) -> None:
    artist = db.query(Artist).filter(Artist.id == int(artist_id)).first()
    if artist is None:
        raise ValueError("Artist not found.")
    if artist.owner_user_id is None or int(artist.owner_user_id) != int(user.id):
        raise PermissionError("Not owner of this artist.")


def _participant_or_404(db: Session, *, release_id: int, artist_id: int) -> ReleaseParticipant:
    row = (
        db.query(ReleaseParticipant)
        .filter(
            ReleaseParticipant.release_id == int(release_id),
            ReleaseParticipant.artist_id == int(artist_id),
        )
        .first()
    )
    if row is None:
        raise ValueError("Participant not found on this release.")
    return row


def list_release_approvals(db: Session, *, release_id: int) -> list[ReleaseParticipant]:
    return (
        db.query(ReleaseParticipant)
        .filter(ReleaseParticipant.release_id == int(release_id))
        .order_by(ReleaseParticipant.artist_id.asc())
        .all()
    )


def is_release_approvable(db: Session, *, release_id: int) -> bool:
    return compute_release_approval_status(db, release_id=release_id) == RELEASE_APPROVAL_STATUS_READY


def compute_release_approval_status(db: Session, *, release_id: int) -> str:
    blocking = (
        db.query(ReleaseParticipant.id)
        .filter(
            ReleaseParticipant.release_id == int(release_id),
            ReleaseParticipant.requires_approval.is_(True),
            ReleaseParticipant.approval_type == RELEASE_PARTICIPANT_APPROVAL_TYPE_SPLIT,
            ReleaseParticipant.status != RELEASE_PARTICIPANT_STATUS_ACCEPTED,
        )
        .first()
    )
    if blocking is not None:
        return RELEASE_APPROVAL_STATUS_PENDING
    return RELEASE_APPROVAL_STATUS_READY


def refresh_release_approval_status(db: Session, *, release_id: int) -> str:
    release = db.query(Release).filter(Release.id == int(release_id)).first()
    if release is None:
        raise ValueError(f"Release {release_id} not found.")
    new_status = compute_release_approval_status(db, release_id=int(release_id))
    if release.approval_status != new_status:
        release.approval_status = new_status
        db.add(release)
    return str(new_status)


def approve_participation(
    db: Session,
    *,
    release_id: int,
    artist_id: int,
    user: User,
) -> ReleaseParticipant:
    _assert_user_owns_artist_or_403(db, user=user, artist_id=int(artist_id))
    participant = _participant_or_404(db, release_id=int(release_id), artist_id=int(artist_id))
    release = db.query(Release).filter(Release.id == int(release_id)).first()
    if release is None:
        raise ValueError(f"Release {release_id} not found.")
    current_split_version = int(release.split_version or 1)
    participant.status = RELEASE_PARTICIPANT_STATUS_ACCEPTED
    participant.approved_at = datetime.now(UTC).replace(tzinfo=None)
    participant.approved_split_version = (
        current_split_version
        if participant.approval_type == RELEASE_PARTICIPANT_APPROVAL_TYPE_SPLIT
        else None
    )
    participant.rejection_reason = None
    db.add(participant)
    refresh_release_approval_status(db, release_id=int(release_id))
    db.commit()
    db.refresh(participant)
    return participant


def reject_participation(
    db: Session,
    *,
    release_id: int,
    artist_id: int,
    user: User,
    reason: str | None = None,
) -> None:
    _assert_user_owns_artist_or_403(db, user=user, artist_id=int(artist_id))
    participant = _participant_or_404(db, release_id=int(release_id), artist_id=int(artist_id))

    participant.status = RELEASE_PARTICIPANT_STATUS_REJECTED
    participant.approved_at = None
    participant.approved_split_version = None
    participant.rejection_reason = (str(reason).strip() if reason else None) or None
    db.add(participant)
    refresh_release_approval_status(db, release_id=int(release_id))
    db.commit()
