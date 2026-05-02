"""GET /playlists/{id}/play — optional auth (requires ``httpx``)."""

from __future__ import annotations

import os

import pytest

pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-do-not-use-in-prod!!")

from app.core.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.role import Role  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.playlist_service import create_playlist  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402


@pytest.fixture()
def playback_client():
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


def test_http_play_public_no_auth(playback_client) -> None:
    client, SessionFactory = playback_client
    db = SessionFactory()
    try:
        db.add(Role(name="user"))
        u = User(email="pb.owner@test.example", username="pb_owner")
        db.add(u)
        db.flush()
        pl = create_playlist(
            db, user_id=int(u.id), title="Public mix", description=None, is_public=True
        )
        db.flush()
        pid = int(pl.id)
        db.commit()
    finally:
        db.close()

    r = client.get(f"/playlists/{pid}/play")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["playlist"]["id"] == pid
    assert data["playlist"]["is_public"] is True
    assert data["tracks"] == []


def test_http_play_private_without_auth_403(playback_client) -> None:
    client, SessionFactory = playback_client
    db = SessionFactory()
    try:
        db.add(Role(name="user"))
        u = User(email="pb.priv@test.example", username="pb_priv")
        db.add(u)
        db.flush()
        pl = create_playlist(
            db, user_id=int(u.id), title="Secret", description=None, is_public=False
        )
        db.flush()
        pid = int(pl.id)
        db.commit()
    finally:
        db.close()

    r = client.get(f"/playlists/{pid}/play")
    assert r.status_code == 403
