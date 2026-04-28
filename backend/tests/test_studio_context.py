from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.artist import Artist
from app.models.label import Label
from app.models.role import Role
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


def test_studio_me_returns_owned_contexts_and_default_current(client_and_session) -> None:
    client, SessionFactory = client_and_session
    email = "studio-owner@example.com"
    token = _register_access_token(client, email)
    user_id = _user_id_by_email(SessionFactory, email)

    db: Session = SessionFactory()
    try:
        db.add(Artist(name="Studio Artist", slug="studio-artist", owner_user_id=user_id))
        db.add(Label(name="Studio Label", owner_user_id=user_id))
        db.commit()
    finally:
        db.close()

    response = client.get(
        "/studio/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert int(body["user"]["id"]) == user_id
    assert body["current_context"] == {"type": "user", "id": user_id}
    assert len(body["allowed_contexts"]["artists"]) == 1
    assert len(body["allowed_contexts"]["labels"]) == 1


def test_studio_context_rejects_unowned_context(client_and_session) -> None:
    client, SessionFactory = client_and_session
    owner_email = "context-owner@example.com"
    _register_access_token(client, owner_email)
    owner_id = _user_id_by_email(SessionFactory, owner_email)

    db: Session = SessionFactory()
    try:
        artist = Artist(name="Other Artist", slug="other-artist", owner_user_id=owner_id)
        db.add(artist)
        db.commit()
        db.refresh(artist)
        artist_id = int(artist.id)
    finally:
        db.close()

    token = _register_access_token(client, "context-other-user@example.com")
    response = client.post(
        "/studio/context",
        headers={"Authorization": f"Bearer {token}"},
        json={"type": "artist", "id": artist_id},
    )
    assert response.status_code == 403


def test_studio_context_persists_owned_artist(client_and_session) -> None:
    client, SessionFactory = client_and_session
    email = "context-setter@example.com"
    token = _register_access_token(client, email)
    user_id = _user_id_by_email(SessionFactory, email)

    db: Session = SessionFactory()
    try:
        artist = Artist(name="Owned Artist", slug="owned-artist", owner_user_id=user_id)
        db.add(artist)
        db.commit()
        db.refresh(artist)
        artist_id = int(artist.id)
    finally:
        db.close()

    set_response = client.post(
        "/studio/context",
        headers={"Authorization": f"Bearer {token}"},
        json={"type": "artist", "id": artist_id},
    )
    assert set_response.status_code == 200, set_response.text
    assert set_response.json()["current_context"] == {"type": "artist", "id": artist_id}

    me_response = client.get(
        "/studio/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_response.status_code == 200, me_response.text
    assert me_response.json()["current_context"] == {"type": "artist", "id": artist_id}
