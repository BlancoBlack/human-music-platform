"""Playlist HTTP smoke (requires ``httpx`` — see ``requirements.txt``)."""

from __future__ import annotations

import os

import pytest

pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-do-not-use-in-prod!!")

from app.core.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.role import Role  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402


@pytest.fixture()
def playlist_http_client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client, TestSession
    app.dependency_overrides.clear()


def test_http_playlists_require_auth(playlist_http_client) -> None:
    client, _ = playlist_http_client
    r = client.post("/playlists", json={"title": "A"})
    assert r.status_code == 401


def test_http_create_playlist(playlist_http_client) -> None:
    client, SessionFactory = playlist_http_client
    db = SessionFactory()
    try:
        db.add(Role(name="user"))
        db.commit()
    finally:
        db.close()

    r = client.post(
        "/auth/register",
        json={"email": "http.pl@test.example", "password": "password1"},
    )
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    r2 = client.post(
        "/playlists",
        json={"title": "HTTP List", "is_public": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["title"] == "HTTP List"
    assert body["is_public"] is True
    assert body["tracks"] == []
