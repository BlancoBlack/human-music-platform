"""Permission enforcement tests for protected backend routes."""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.artist import Artist
from app.models.permission import Permission
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.user import User
from app.models.user_role import UserRole
from app.services.song_ingestion_service import SongIngestionService

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
        db.add_all(
            [
                Role(name="listener"),
                Role(name="user"),
                Role(name="artist_editor"),
                Role(name="admin"),
                Permission(name="edit_own_artist"),
                Permission(name="admin_full_access"),
            ]
        )
        db.flush()
        roles = {r.name: int(r.id) for r in db.query(Role).all()}
        perms = {p.name: int(p.id) for p in db.query(Permission).all()}
        db.add_all(
            [
                RolePermission(
                    role_id=roles["artist_editor"],
                    permission_id=perms["edit_own_artist"],
                ),
                RolePermission(
                    role_id=roles["admin"],
                    permission_id=perms["admin_full_access"],
                ),
            ]
        )
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


def _assign_role(SessionFactory, email: str, role_name: str) -> None:
    db: Session = SessionFactory()
    try:
        user = db.query(User).filter(User.email == email).one()
        db.add(UserRole(user_id=int(user.id), role=role_name))
        db.commit()
    finally:
        db.close()


def _create_artist(SessionFactory, *, owner_user_id: int | None = None) -> int:
    db: Session = SessionFactory()
    try:
        artist = Artist(name="Permission Artist", owner_user_id=owner_user_id)
        db.add(artist)
        db.commit()
        db.refresh(artist)
        return int(artist.id)
    finally:
        db.close()


def _user_id_by_email(SessionFactory, email: str) -> int:
    db: Session = SessionFactory()
    try:
        user = db.query(User).filter(User.email == email).one()
        return int(user.id)
    finally:
        db.close()


def test_legacy_upload_requires_artist_ownership(client_and_session) -> None:
    client, SessionFactory = client_and_session
    token = _register_access_token(client, "no-upload@example.com")
    owner_email = "legacy-owner@example.com"
    _register_access_token(client, owner_email)
    owner_id = _user_id_by_email(SessionFactory, owner_email)
    artist_id = _create_artist(SessionFactory, owner_user_id=owner_id)

    response = client.post(
        f"/artists/{artist_id}/songs",
        headers={"Authorization": f"Bearer {token}"},
        data={"title": "Track"},
        files={"file": ("audio.wav", b"fake", "audio/wav")},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Not owner of this artist"


def test_legacy_upload_non_owner_forbidden(
    monkeypatch: pytest.MonkeyPatch, client_and_session
) -> None:
    client, SessionFactory = client_and_session
    owner_email = "artist-owner@example.com"
    owner_token = _register_access_token(client, owner_email)
    owner_id = _user_id_by_email(SessionFactory, owner_email)
    artist_id = _create_artist(SessionFactory, owner_user_id=owner_id)
    _assign_role(SessionFactory, owner_email, "artist_editor")

    email = "can-upload-not-owner@example.com"
    token = _register_access_token(client, email)
    _assign_role(SessionFactory, email, "artist_editor")

    def _fake_create_song(self, **kwargs):
        return SimpleNamespace(
            id=999,
            title=str(kwargs["title"]),
            upload_status="ready",
            duration_seconds=123,
        )

    monkeypatch.setattr(SongIngestionService, "create_song", _fake_create_song)

    response = client.post(
        f"/artists/{artist_id}/songs",
        headers={"Authorization": f"Bearer {token}"},
        data={"title": "Forbidden Ownership Track"},
        files={"file": ("audio.wav", b"fake", "audio/wav")},
    )
    assert response.status_code == 403
    assert response.json()["detail"] in (
        "Not allowed to modify this artist",
        "Not owner of this artist",
    )

    # Owner path still works with same permissions.
    owner_response = client.post(
        f"/artists/{artist_id}/songs",
        headers={"Authorization": f"Bearer {owner_token}"},
        data={"title": "Owner Track"},
        files={"file": ("audio.wav", b"fake", "audio/wav")},
    )
    assert owner_response.status_code == 200, owner_response.text
    body = owner_response.json()
    assert body["song_id"] == 999
    assert body["title"] == "Owner Track"


def test_legacy_upload_admin_bypasses_ownership(
    monkeypatch: pytest.MonkeyPatch, client_and_session
) -> None:
    client, SessionFactory = client_and_session
    owner_email = "another-owner@example.com"
    _register_access_token(client, owner_email)
    owner_id = _user_id_by_email(SessionFactory, owner_email)
    artist_id = _create_artist(SessionFactory, owner_user_id=owner_id)

    admin_email = "admin-upload@example.com"
    admin_token = _register_access_token(client, admin_email)
    _assign_role(SessionFactory, admin_email, "admin")

    def _fake_create_song(self, **kwargs):
        return SimpleNamespace(
            id=999,
            title=str(kwargs["title"]),
            upload_status="ready",
            duration_seconds=123,
        )

    monkeypatch.setattr(SongIngestionService, "create_song", _fake_create_song)

    response = client.post(
        f"/artists/{artist_id}/songs",
        headers={"Authorization": f"Bearer {admin_token}"},
        data={"title": "Admin Track"},
        files={"file": ("audio.wav", b"fake", "audio/wav")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["song_id"] == 999
    assert body["title"] == "Admin Track"


def test_admin_payouts_requires_admin_role(client_and_session) -> None:
    client, SessionFactory = client_and_session
    token_denied = _register_access_token(client, "admin-denied@example.com")
    denied = client.get(
        "/admin/payouts",
        headers={"Authorization": f"Bearer {token_denied}"},
    )
    assert denied.status_code == 403
    assert denied.json()["detail"] in (
        "Admin role is not configured",
        "Admin access required",
    )

    email = "admin-allowed@example.com"
    token_allowed = _register_access_token(client, email)
    _assign_role(SessionFactory, email, "admin")
    allowed = client.get(
        "/admin/payouts",
        headers={"Authorization": f"Bearer {token_allowed}"},
    )
    assert allowed.status_code == 200, allowed.text
    assert isinstance(allowed.json(), list)
