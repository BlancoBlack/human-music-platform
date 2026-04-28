from __future__ import annotations

import os
from datetime import datetime, timedelta

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
    RELEASE_TYPE_ALBUM,
    RELEASE_TYPE_SINGLE,
    Release,
)
from app.models.release_media_asset import (
    RELEASE_MEDIA_ASSET_TYPE_COVER_ART,
    ReleaseMediaAsset,
)
from app.models.release_participant import (
    RELEASE_PARTICIPANT_APPROVAL_TYPE_FEATURE,
    RELEASE_PARTICIPANT_APPROVAL_TYPE_SPLIT,
    RELEASE_PARTICIPANT_ROLE_COLLABORATOR,
    RELEASE_PARTICIPANT_ROLE_FEATURED,
    RELEASE_PARTICIPANT_ROLE_PRIMARY,
    RELEASE_PARTICIPANT_STATUS_ACCEPTED,
    RELEASE_PARTICIPANT_STATUS_PENDING,
    RELEASE_PARTICIPANT_STATUS_REJECTED,
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


def _seed_release_payload(
    SessionFactory,
    *,
    release_id: int,
    release_slug: str,
    release_title: str,
    release_type: str,
    release_artist_id: int,
    created_at: datetime,
    updated_at: datetime,
    pending_rows: list[tuple[int, str, str]],
    extra_participants: list[tuple[int, str, str, str, bool, str | None, datetime | None]] | None = None,
) -> None:
    db: Session = SessionFactory()
    try:
        genre = db.query(Genre).filter(Genre.id == 1).first()
        if genre is None:
            db.add(Genre(id=1, name="Hip Hop", slug="hip-hop"))
            db.flush()

        release = Release(
            id=release_id,
            slug=release_slug,
            title=release_title,
            artist_id=int(release_artist_id),
            type=release_type,
            release_date=created_at,
            state=RELEASE_STATE_DRAFT,
            approval_status=RELEASE_APPROVAL_STATUS_PENDING,
            split_version=1,
            created_at=created_at,
            updated_at=updated_at,
        )
        db.add(release)
        db.flush()

        db.add(
            ReleaseMediaAsset(
                release_id=release_id,
                asset_type=RELEASE_MEDIA_ASSET_TYPE_COVER_ART,
                file_path=f"covers/{release_slug}.png",
            )
        )

        song_a = Song(
            slug=f"{release_slug}-a",
            title=f"{release_title} Song A",
            artist_id=int(release_artist_id),
            release_id=release_id,
            upload_status="draft",
            state=SONG_STATE_DRAFT,
            genre_id=1,
            moods=["energetic", "uplifting"],
            country_code="US",
            city="LA",
            created_at=created_at,
            updated_at=updated_at,
        )
        song_b = Song(
            slug=f"{release_slug}-b",
            title=f"{release_title} Song B",
            artist_id=int(release_artist_id),
            release_id=release_id,
            upload_status="draft",
            state=SONG_STATE_DRAFT,
            genre_id=1,
            moods=["uplifting", "calm"],
            country_code="US",
            city="LA",
            created_at=created_at,
            updated_at=updated_at,
        )
        db.add_all([song_a, song_b])
        db.flush()

        db.add_all(
            [
                SongArtistSplit(song_id=int(song_a.id), artist_id=int(release_artist_id), share=0.7, split_bps=7000, version=1),
                SongArtistSplit(song_id=int(song_a.id), artist_id=1002, share=0.3, split_bps=3000, version=1),
                SongArtistSplit(song_id=int(song_b.id), artist_id=int(release_artist_id), share=0.6, split_bps=6000, version=1),
                SongArtistSplit(song_id=int(song_b.id), artist_id=1002, share=0.4, split_bps=4000, version=1),
            ]
        )
        db.add(SongFeaturedArtist(song_id=int(song_a.id), artist_id=1003, position=1))
        db.add(SongCreditEntry(song_id=int(song_a.id), display_name="Producer X", role="producer", position=1))
        db.add(SongCreditEntry(song_id=int(song_b.id), display_name="Mix Y", role="mix engineer", position=1))

        db.add(
            ReleaseParticipant(
                release_id=release_id,
                artist_id=int(release_artist_id),
                role=RELEASE_PARTICIPANT_ROLE_PRIMARY,
                status=RELEASE_PARTICIPANT_STATUS_ACCEPTED,
                approval_type=RELEASE_PARTICIPANT_APPROVAL_TYPE_SPLIT,
                requires_approval=True,
                approved_at=created_at,
            )
        )
        for artist_id, role, approval_type in pending_rows:
            db.add(
                ReleaseParticipant(
                    release_id=release_id,
                    artist_id=int(artist_id),
                    role=role,
                    status=RELEASE_PARTICIPANT_STATUS_PENDING,
                    approval_type=approval_type,
                    requires_approval=True,
                )
            )

        for row in (extra_participants or []):
            aid, role, status, approval_type, requires_approval, rejection_reason, approved_at = row
            db.add(
                ReleaseParticipant(
                    release_id=release_id,
                    artist_id=int(aid),
                    role=role,
                    status=status,
                    approval_type=approval_type,
                    requires_approval=requires_approval,
                    rejection_reason=rejection_reason,
                    approved_at=approved_at,
                )
            )
        db.commit()
    finally:
        db.close()


def _seed_artists(SessionFactory, *, owner_user_id: int, other_user_id: int) -> None:
    db: Session = SessionFactory()
    try:
        db.add_all(
            [
                Artist(id=1001, name="Main Artist", payout_method="none", owner_user_id=owner_user_id),
                Artist(id=1002, name="Owned Collaborator", payout_method="none", owner_user_id=owner_user_id),
                Artist(id=1003, name="Featured Artist", payout_method="none", owner_user_id=other_user_id),
                Artist(id=1004, name="Other Owned", payout_method="none", owner_user_id=other_user_id),
            ]
        )
        db.commit()
    finally:
        db.close()


def test_pending_approvals_enriched_payload_and_ordering(client_and_session) -> None:
    client, SessionFactory = client_and_session
    token = _register_access_token(client, "approvals.user@example.com")
    user_id = _user_id_by_email(SessionFactory, "approvals.user@example.com")
    _register_access_token(client, "other.user@example.com")
    other_user_id = _user_id_by_email(SessionFactory, "other.user@example.com")

    _seed_artists(SessionFactory, owner_user_id=user_id, other_user_id=other_user_id)

    now = datetime.utcnow()
    _seed_release_payload(
        SessionFactory,
        release_id=1,
        release_slug="release-blocking",
        release_title="Blocking Pending",
        release_type=RELEASE_TYPE_ALBUM,
        release_artist_id=1001,
        created_at=now - timedelta(days=3),
        updated_at=now - timedelta(hours=1),
        pending_rows=[
            (1002, RELEASE_PARTICIPANT_ROLE_COLLABORATOR, RELEASE_PARTICIPANT_APPROVAL_TYPE_SPLIT),
        ],
        extra_participants=[
            (
                1003,
                RELEASE_PARTICIPANT_ROLE_COLLABORATOR,
                RELEASE_PARTICIPANT_STATUS_REJECTED,
                RELEASE_PARTICIPANT_APPROVAL_TYPE_FEATURE,
                True,
                "Need better terms",
                None,
            ),
        ],
    )
    _seed_release_payload(
        SessionFactory,
        release_id=2,
        release_slug="release-feature-only",
        release_title="Feature Pending",
        release_type=RELEASE_TYPE_SINGLE,
        release_artist_id=1001,
        created_at=now - timedelta(days=2),
        updated_at=now,
        pending_rows=[
            (1002, RELEASE_PARTICIPANT_ROLE_COLLABORATOR, RELEASE_PARTICIPANT_APPROVAL_TYPE_FEATURE),
        ],
    )
    _seed_release_payload(
        SessionFactory,
        release_id=3,
        release_slug="release-unrelated",
        release_title="Unrelated Pending",
        release_type=RELEASE_TYPE_SINGLE,
        release_artist_id=1001,
        created_at=now - timedelta(days=1),
        updated_at=now + timedelta(hours=1),
        pending_rows=[
            (1004, RELEASE_PARTICIPANT_ROLE_COLLABORATOR, RELEASE_PARTICIPANT_APPROVAL_TYPE_SPLIT),
        ],
    )

    response = client.get(
        "/studio/pending-approvals",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert [int(item["release"]["id"]) for item in body] == [1, 2]

    first = body[0]
    assert first["release"]["title"] == "Blocking Pending"
    assert first["release"]["type"] == "album"
    assert int(first["release"]["split_version"]) == 1
    assert first["release"]["cover_url"] is not None
    assert int(first["release"]["track_count"]) == 2
    assert first["release"]["genres"] == ["Hip Hop"]
    assert sorted(first["release"]["moods"]) == ["calm", "energetic", "uplifting"]
    assert first["release"]["location"] == "LA, US"
    assert len(first["songs"]) == 2
    assert any(song["featured_artists"] for song in first["songs"])
    assert any(song["credits"] for song in first["songs"])
    assert len(first["splits"]) == 2
    owned_split = next(s for s in first["splits"] if int(s["artist_id"]) == 1002)
    assert float(owned_split["share"]) > 0

    assert first["pending_summary"] == {"split": 1, "feature": 0}

    participants_order = [int(p["artist_id"]) for p in first["participants"]]
    assert participants_order == [1002, 1001, 1003]
    participant_by_id = {int(p["artist_id"]): p for p in first["participants"]}
    assert participant_by_id[1002]["is_actionable_for_user"] is True
    assert participant_by_id[1002]["has_feature_context"] is False
    assert participant_by_id[1001]["is_actionable_for_user"] is False
    assert participant_by_id[1003]["is_actionable_for_user"] is False
    assert participant_by_id[1003]["has_feature_context"] is True

    participant = next(p for p in first["participants"] if int(p["artist_id"]) == 1003)
    assert participant["status"] == "rejected"
    assert participant["rejection_reason"] == "Need better terms"
    assert participant["blocking"] is False

    second = body[1]
    assert second["release"]["title"] == "Feature Pending"
    assert second["pending_summary"] == {"split": 0, "feature": 1}
    second_participant_by_id = {int(p["artist_id"]): p for p in second["participants"]}
    assert second_participant_by_id[1002]["is_actionable_for_user"] is True


def test_pending_approvals_view_list_is_lightweight(client_and_session) -> None:
    client, SessionFactory = client_and_session
    token = _register_access_token(client, "approvals.list@example.com")
    user_id = _user_id_by_email(SessionFactory, "approvals.list@example.com")
    _register_access_token(client, "approvals.list.other@example.com")
    other_user_id = _user_id_by_email(SessionFactory, "approvals.list.other@example.com")
    _seed_artists(SessionFactory, owner_user_id=user_id, other_user_id=other_user_id)

    now = datetime.utcnow()
    _seed_release_payload(
        SessionFactory,
        release_id=11,
        release_slug="release-list-view",
        release_title="List View Release",
        release_type=RELEASE_TYPE_SINGLE,
        release_artist_id=1001,
        created_at=now - timedelta(days=1),
        updated_at=now,
        pending_rows=[
            (1002, RELEASE_PARTICIPANT_ROLE_COLLABORATOR, RELEASE_PARTICIPANT_APPROVAL_TYPE_SPLIT),
        ],
    )

    response = client.get(
        "/studio/pending-approvals?view=list",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 1
    item = body[0]
    assert set(item.keys()) == {"release", "approval_status", "pending_summary", "participants"}
    assert set(item["release"].keys()) == {
        "id",
        "title",
        "cover_url",
        "artist",
        "type",
        "created_at",
        "track_count",
        "split_version",
    }
    participant = item["participants"][0]
    assert set(participant.keys()) == {
        "artist_id",
        "artist_name",
        "role",
        "status",
        "approval_type",
        "blocking",
        "is_actionable_for_user",
    }


def test_pending_approvals_list_view_includes_actionable_flag(client_and_session) -> None:
    client, SessionFactory = client_and_session
    token = _register_access_token(client, "approvals.list.flag@example.com")
    user_id = _user_id_by_email(SessionFactory, "approvals.list.flag@example.com")
    _register_access_token(client, "approvals.list.flag.other@example.com")
    other_user_id = _user_id_by_email(SessionFactory, "approvals.list.flag.other@example.com")
    _seed_artists(SessionFactory, owner_user_id=user_id, other_user_id=other_user_id)

    now = datetime.utcnow()
    _seed_release_payload(
        SessionFactory,
        release_id=61,
        release_slug="release-list-actionable-flag",
        release_title="List Actionable Flag",
        release_type=RELEASE_TYPE_SINGLE,
        release_artist_id=1001,
        created_at=now - timedelta(hours=2),
        updated_at=now,
        pending_rows=[
            (1002, RELEASE_PARTICIPANT_ROLE_COLLABORATOR, RELEASE_PARTICIPANT_APPROVAL_TYPE_SPLIT),
            (1003, RELEASE_PARTICIPANT_ROLE_FEATURED, RELEASE_PARTICIPANT_APPROVAL_TYPE_FEATURE),
        ],
    )

    res = client.get(
        "/studio/pending-approvals?view=list",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200, res.text
    for release in res.json():
        for participant in release["participants"]:
            assert "is_actionable_for_user" in participant


def test_pending_approvals_empty_when_user_has_no_pending(client_and_session) -> None:
    client, SessionFactory = client_and_session
    token = _register_access_token(client, "none.pending@example.com")
    user_id = _user_id_by_email(SessionFactory, "none.pending@example.com")
    _register_access_token(client, "other.none@example.com")
    other_user_id = _user_id_by_email(SessionFactory, "other.none@example.com")
    _seed_artists(SessionFactory, owner_user_id=user_id, other_user_id=other_user_id)

    now = datetime.utcnow()
    _seed_release_payload(
        SessionFactory,
        release_id=10,
        release_slug="release-none",
        release_title="No Pending",
        release_type=RELEASE_TYPE_SINGLE,
        release_artist_id=1001,
        created_at=now - timedelta(days=1),
        updated_at=now - timedelta(hours=1),
        pending_rows=[],
        extra_participants=[
            (
                1002,
                RELEASE_PARTICIPANT_ROLE_COLLABORATOR,
                RELEASE_PARTICIPANT_STATUS_ACCEPTED,
                RELEASE_PARTICIPANT_APPROVAL_TYPE_SPLIT,
                True,
                None,
                now - timedelta(hours=2),
            ),
        ],
    )

    response = client.get(
        "/studio/pending-approvals",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    assert response.json() == []
