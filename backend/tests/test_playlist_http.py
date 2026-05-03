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


def test_http_playlists_list_requires_auth(playlist_http_client) -> None:
    client, _ = playlist_http_client
    assert client.get("/playlists").status_code == 401


def test_http_playlists_list_owner_metadata_only(playlist_http_client) -> None:
    client, SessionFactory = playlist_http_client
    db = SessionFactory()
    try:
        db.add(Role(name="user"))
        db.commit()
    finally:
        db.close()

    r = client.post(
        "/auth/register",
        json={"email": "pl.list.a@test.example", "password": "password1"},
    )
    token_a = r.json()["access_token"]
    r = client.post(
        "/auth/register",
        json={"email": "pl.list.b@test.example", "password": "password1"},
    )
    token_b = r.json()["access_token"]

    r_create = client.post(
        "/playlists",
        json={"title": "Mine", "is_public": False},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert r_create.status_code == 200
    pid = r_create.json()["id"]

    r_empty = client.get("/playlists", headers={"Authorization": f"Bearer {token_b}"})
    assert r_empty.status_code == 200
    empty_body = r_empty.json()["playlists"]
    assert len(empty_body) == 1
    assert empty_body[0]["title"] == "Liked Songs"
    assert empty_body[0]["is_public"] is False
    assert empty_body[0]["thumbnail_urls"] == []

    r_list = client.get("/playlists", headers={"Authorization": f"Bearer {token_a}"})
    assert r_list.status_code == 200
    body = r_list.json()["playlists"]
    assert len(body) == 2
    assert body[0]["title"] == "Liked Songs"
    assert body[0]["is_public"] is False
    assert body[0]["thumbnail_urls"] == []
    assert body[1] == {
        "id": pid,
        "title": "Mine",
        "is_public": False,
        "thumbnail_urls": [],
    }


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


def test_http_playlist_detail_enriched_empty(playlist_http_client) -> None:
    """GET /playlists/{id} returns cover_urls + enriched track shape (may be empty)."""
    client, SessionFactory = playlist_http_client
    db = SessionFactory()
    try:
        db.add(Role(name="user"))
        db.commit()
    finally:
        db.close()

    r = client.post(
        "/auth/register",
        json={"email": "pl.detail.empty@test.example", "password": "password1"},
    )
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]

    r_create = client.post(
        "/playlists",
        json={"title": "Empty detail", "is_public": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r_create.status_code == 200
    pid = r_create.json()["id"]

    r_detail = client.get(
        f"/playlists/{pid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r_detail.status_code == 200, r_detail.text
    detail = r_detail.json()
    assert detail["id"] == pid
    assert detail["title"] == "Empty detail"
    assert detail["cover_urls"] == []
    assert detail["tracks"] == []
