from __future__ import annotations

import os
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.artist import Artist
from app.models.genre import Genre
from app.models.release import (
    RELEASE_APPROVAL_STATUS_PENDING,
    RELEASE_STATE_DRAFT,
    RELEASE_TYPE_SINGLE,
    Release,
)
from app.models.release_participant import (
    RELEASE_PARTICIPANT_APPROVAL_TYPE_FEATURE,
    RELEASE_PARTICIPANT_APPROVAL_TYPE_SPLIT,
    RELEASE_PARTICIPANT_ROLE_COLLABORATOR,
    RELEASE_PARTICIPANT_ROLE_PRIMARY,
    RELEASE_PARTICIPANT_STATUS_ACCEPTED,
    RELEASE_PARTICIPANT_STATUS_PENDING,
    ReleaseParticipant,
)
from app.models.role import Role
from app.models.song import SONG_STATE_DRAFT, Song
from app.models.song_artist_split import SongArtistSplit
from app.models.song_credit_entry import SongCreditEntry
from app.models.song_featured_artist import SongFeaturedArtist
from app.models.user import User

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-do-not-use-in-prod!!")


@pytest.fixture()
def client_and_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)

    db = TestSession()
    try:
        db.add_all([Role(name="user"), Role(name="artist"), Role(name="admin")])
        db.commit()
    finally:
        db.close()

    def override_get_db():
        tdb = TestSession()
        try:
            yield tdb
        finally:
            tdb.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client, TestSession
    app.dependency_overrides.clear()


def _register_access_token(client: TestClient, email: str) -> str:
    response = client.post(
        "/auth/register",
        json={"email": email, "password": "password1"},
    )
    assert response.status_code == 200, response.text
    return str(response.json()["access_token"])


def _user_id_by_email(SessionFactory, email: str) -> int:
    db: Session = SessionFactory()
    try:
        user = db.query(User).filter(User.email == email).one()
        return int(user.id)
    finally:
        db.close()


def _seed_release(SessionFactory, *, owner_user_id: int, other_user_id: int) -> int:
    db: Session = SessionFactory()
    try:
        db.add(Genre(id=1, name="Hip Hop", slug="hip-hop"))
        db.add_all(
            [
                Artist(id=5001, name="Main Artist", payout_method="none", owner_user_id=owner_user_id),
                Artist(id=5002, name="Owned Collaborator", payout_method="none", owner_user_id=owner_user_id),
                Artist(id=5003, name="Feature Artist", payout_method="none", owner_user_id=other_user_id),
                Artist(id=5004, name="Unrelated Artist", payout_method="none", owner_user_id=other_user_id),
            ]
        )
        release = Release(
            id=9001,
            slug="release-detail",
            title="Release Detail",
            artist_id=5001,
            type=RELEASE_TYPE_SINGLE,
            release_date=datetime.utcnow(),
            state=RELEASE_STATE_DRAFT,
            approval_status=RELEASE_APPROVAL_STATUS_PENDING,
            split_version=1,
        )
        db.add(release)
        db.flush()
        song = Song(
            slug="release-detail-song",
            title="Release Detail Song",
            artist_id=5001,
            release_id=9001,
            upload_status="draft",
            state=SONG_STATE_DRAFT,
            genre_id=1,
            moods=["calm"],
            country_code="US",
            city="NYC",
        )
        db.add(song)
        db.flush()
        db.add_all(
            [
                SongArtistSplit(song_id=int(song.id), artist_id=5001, share=0.7, split_bps=7000, version=1),
                SongArtistSplit(song_id=int(song.id), artist_id=5002, share=0.3, split_bps=3000, version=1),
                SongFeaturedArtist(song_id=int(song.id), artist_id=5003, position=1),
                SongCreditEntry(song_id=int(song.id), display_name="Producer A", role="producer", position=1),
                ReleaseParticipant(
                    release_id=9001,
                    artist_id=5001,
                    role=RELEASE_PARTICIPANT_ROLE_PRIMARY,
                    status=RELEASE_PARTICIPANT_STATUS_ACCEPTED,
                    approval_type=RELEASE_PARTICIPANT_APPROVAL_TYPE_SPLIT,
                    requires_approval=True,
                ),
                ReleaseParticipant(
                    release_id=9001,
                    artist_id=5002,
                    role=RELEASE_PARTICIPANT_ROLE_COLLABORATOR,
                    status=RELEASE_PARTICIPANT_STATUS_PENDING,
                    approval_type=RELEASE_PARTICIPANT_APPROVAL_TYPE_SPLIT,
                    requires_approval=True,
                ),
                ReleaseParticipant(
                    release_id=9001,
                    artist_id=5003,
                    role=RELEASE_PARTICIPANT_ROLE_COLLABORATOR,
                    status=RELEASE_PARTICIPANT_STATUS_PENDING,
                    approval_type=RELEASE_PARTICIPANT_APPROVAL_TYPE_FEATURE,
                    requires_approval=True,
                ),
            ]
        )
        db.commit()
        return 9001
    finally:
        db.close()


def _seed_release_accepted_only_access(
    SessionFactory,
    *,
    accepted_owner_user_id: int,
    other_user_id: int,
) -> int:
    db: Session = SessionFactory()
    try:
        db.add(Genre(id=2, name="Pop", slug="pop"))
        db.add_all(
            [
                Artist(id=5101, name="Accepted Owner Artist", payout_method="none", owner_user_id=accepted_owner_user_id),
                Artist(id=5102, name="Other Pending Split", payout_method="none", owner_user_id=other_user_id),
                Artist(id=5103, name="Other Pending Feature", payout_method="none", owner_user_id=other_user_id),
            ]
        )
        release = Release(
            id=9002,
            slug="release-accepted-only",
            title="Release Accepted Only",
            artist_id=5101,
            type=RELEASE_TYPE_SINGLE,
            release_date=datetime.utcnow(),
            state=RELEASE_STATE_DRAFT,
            approval_status=RELEASE_APPROVAL_STATUS_PENDING,
            split_version=1,
        )
        db.add(release)
        db.flush()
        song = Song(
            slug="release-accepted-only-song",
            title="Accepted Only Song",
            artist_id=5101,
            release_id=9002,
            upload_status="draft",
            state=SONG_STATE_DRAFT,
            genre_id=2,
            moods=["focused"],
            country_code="US",
            city="SF",
        )
        db.add(song)
        db.flush()
        db.add_all(
            [
                SongArtistSplit(song_id=int(song.id), artist_id=5101, share=0.8, split_bps=8000, version=1),
                SongArtistSplit(song_id=int(song.id), artist_id=5102, share=0.2, split_bps=2000, version=1),
                SongFeaturedArtist(song_id=int(song.id), artist_id=5103, position=1),
                ReleaseParticipant(
                    release_id=9002,
                    artist_id=5101,
                    role=RELEASE_PARTICIPANT_ROLE_PRIMARY,
                    status=RELEASE_PARTICIPANT_STATUS_ACCEPTED,
                    approval_type=RELEASE_PARTICIPANT_APPROVAL_TYPE_SPLIT,
                    requires_approval=True,
                ),
                ReleaseParticipant(
                    release_id=9002,
                    artist_id=5102,
                    role=RELEASE_PARTICIPANT_ROLE_COLLABORATOR,
                    status=RELEASE_PARTICIPANT_STATUS_PENDING,
                    approval_type=RELEASE_PARTICIPANT_APPROVAL_TYPE_SPLIT,
                    requires_approval=True,
                ),
                ReleaseParticipant(
                    release_id=9002,
                    artist_id=5103,
                    role=RELEASE_PARTICIPANT_ROLE_COLLABORATOR,
                    status=RELEASE_PARTICIPANT_STATUS_PENDING,
                    approval_type=RELEASE_PARTICIPANT_APPROVAL_TYPE_FEATURE,
                    requires_approval=True,
                ),
            ]
        )
        db.commit()
        return 9002
    finally:
        db.close()


def test_release_detail_access_and_payload(client_and_session) -> None:
    client, SessionFactory = client_and_session
    token = _register_access_token(client, "detail.owner@example.com")
    owner_id = _user_id_by_email(SessionFactory, "detail.owner@example.com")
    _register_access_token(client, "detail.other@example.com")
    other_id = _user_id_by_email(SessionFactory, "detail.other@example.com")

    release_id = _seed_release(SessionFactory, owner_user_id=owner_id, other_user_id=other_id)

    response = client.get(
        f"/studio/releases/{release_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert int(body["release"]["id"]) == release_id
    assert body["release"]["approval_status"] == "pending_approvals"
    assert int(body["release"]["split_version"]) == 1
    assert int(body["release"]["track_count"]) == 1
    assert body["user_context"]["pending_actions_count"] == 1
    assert 5002 in body["user_context"]["owned_artist_ids"]
    assert len(body["songs"]) == 1
    assert len(body["splits"]) == 2
    assert len(body["participants"]) == 3
    assert body["pending_summary"] == {"split": 1, "feature": 0}
    participants_order = [int(p["artist_id"]) for p in body["participants"]]
    assert participants_order == [5002, 5003, 5001]
    participant_by_id = {int(p["artist_id"]): p for p in body["participants"]}
    assert participant_by_id[5002]["is_actionable_for_user"] is True
    assert participant_by_id[5002]["has_feature_context"] is False
    assert participant_by_id[5003]["is_actionable_for_user"] is False
    assert participant_by_id[5003]["has_feature_context"] is True
    assert participant_by_id[5001]["is_actionable_for_user"] is False


def test_release_detail_returns_404_for_unrelated_user(client_and_session) -> None:
    client, SessionFactory = client_and_session
    token = _register_access_token(client, "detail.unrelated@example.com")
    _register_access_token(client, "detail.creator@example.com")
    creator_id = _user_id_by_email(SessionFactory, "detail.creator@example.com")
    _register_access_token(client, "detail.third@example.com")
    third_user_id = _user_id_by_email(SessionFactory, "detail.third@example.com")

    release_id = _seed_release(SessionFactory, owner_user_id=creator_id, other_user_id=third_user_id)

    response = client.get(
        f"/studio/releases/{release_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


def test_release_approve_reject_action_feedback_shape(client_and_session) -> None:
    client, SessionFactory = client_and_session
    token = _register_access_token(client, "detail.actions@example.com")
    owner_id = _user_id_by_email(SessionFactory, "detail.actions@example.com")
    _register_access_token(client, "detail.actions.other@example.com")
    other_id = _user_id_by_email(SessionFactory, "detail.actions.other@example.com")
    release_id = _seed_release(SessionFactory, owner_user_id=owner_id, other_user_id=other_id)

    approve = client.post(
        f"/studio/releases/{release_id}/approve",
        headers={"Authorization": f"Bearer {token}"},
        json={"artist_id": 5002},
    )
    assert approve.status_code == 200, approve.text
    approve_body = approve.json()
    assert approve_body["status"] == "accepted"
    assert approve_body["updated_participant"]["blocking"] is True
    assert approve_body["release_approval_status"] in {"pending_approvals", "ready"}

    reject = client.post(
        f"/studio/releases/{release_id}/reject",
        headers={"Authorization": f"Bearer {token}"},
        json={"artist_id": 5002, "reason": "Not acceptable"},
    )
    assert reject.status_code == 200, reject.text
    reject_body = reject.json()
    assert reject_body["status"] == "rejected"
    assert reject_body["updated_participant"]["status"] == "rejected"
    assert reject_body["updated_participant"]["blocking"] is True
    assert reject_body["release_approval_status"] in {"pending_approvals", "ready"}


def test_release_detail_access_allowed_with_only_accepted_owned_participant(client_and_session) -> None:
    client, SessionFactory = client_and_session
    token = _register_access_token(client, "accepted.owner@example.com")
    accepted_owner_id = _user_id_by_email(SessionFactory, "accepted.owner@example.com")
    _register_access_token(client, "accepted.other@example.com")
    other_id = _user_id_by_email(SessionFactory, "accepted.other@example.com")
    release_id = _seed_release_accepted_only_access(
        SessionFactory,
        accepted_owner_user_id=accepted_owner_id,
        other_user_id=other_id,
    )

    response = client.get(
        f"/studio/releases/{release_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert int(body["release"]["id"]) == release_id
    assert body["user_context"]["pending_actions_count"] == 0
    assert body["pending_summary"] == {"split": 0, "feature": 0}
