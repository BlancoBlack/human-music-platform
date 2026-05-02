"""Like HTTP endpoints (requires ``httpx``)."""

from __future__ import annotations

import os

import pytest

pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-do-not-use-in-prod!!")

from app.core.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.artist import Artist  # noqa: E402
from app.models.role import Role  # noqa: E402
from app.models.song import SONG_STATE_DRAFT, Song  # noqa: E402
from app.models.user import User  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402


@pytest.fixture()
def like_http_client():
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


def test_like_requires_auth(like_http_client) -> None:
    client, _ = like_http_client
    r = client.post("/like", json={"song_id": 1})
    assert r.status_code == 401


def test_like_flow_http(like_http_client) -> None:
    client, SessionFactory = like_http_client
    db = SessionFactory()
    try:
        db.add(Role(name="user"))
        seed_u = User(email="lk.seed@test.example", username="lk_seed")
        db.add(seed_u)
        db.flush()
        a = Artist(slug="lk-art", name="LK", owner_user_id=int(seed_u.id))
        db.add(a)
        db.flush()
        db.add(
            Song(
                slug="lk-song",
                title="S",
                artist_id=a.id,
                upload_status="ready",
                state=SONG_STATE_DRAFT,
            )
        )
        db.commit()
        sid = int(db.query(Song.id).scalar())
    finally:
        db.close()

    r = client.post(
        "/auth/register",
        json={"email": "lk.liker@test.example", "password": "password1"},
    )
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]

    r2 = client.post(
        "/like",
        json={"song_id": sid},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json() == {"song_id": sid, "liked": True}

    r3 = client.post(
        "/like",
        json={"song_id": sid},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r3.status_code == 200, r3.text

    db = SessionFactory()
    try:
        uid = int(db.query(User.id).filter(User.email == "lk.liker@test.example").scalar())
        from app.models.like_event import LikeEvent  # noqa: PLC0415

        assert db.query(LikeEvent).filter_by(user_id=uid, song_id=sid).count() == 1
    finally:
        db.close()

    r4 = client.delete(
        "/like",
        params={"song_id": sid},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r4.status_code == 200, r4.text
    assert r4.json()["liked"] is False
