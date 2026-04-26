from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-do-not-use-in-prod!!")

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.role import Role
from app.models.user import User


@pytest.fixture()
def client_and_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    seed_db = TestSession()
    try:
        seed_db.add_all([Role(name="user"), Role(name="artist"), Role(name="label")])
        seed_db.commit()
    finally:
        seed_db.close()

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


def _register_user(client: TestClient, email: str = "flow.user@example.com") -> dict:
    r = client.post(
        "/auth/register",
        json={"email": email, "password": "password1", "role": "user"},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_onboarding_state_machine_valid_progression(client_and_session) -> None:
    client, SessionFactory = client_and_session
    reg = _register_user(client)
    token = reg["access_token"]
    assert reg["onboarding_step"] == "REGISTERED"
    assert reg["onboarding_completed"] is False

    p = client.post(
        "/onboarding/preferences",
        json={"genres": ["Hip-Hop"], "artists": ["Artist X"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert p.status_code == 200, p.text
    assert p.json()["onboarding_step"] == "COMPLETED"

    s = client.post(
        "/discovery/first-session",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert s.status_code == 200, s.text
    assert s.json()["mode"] == "onboarding"

    c = client.post(
        "/onboarding/complete",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert c.status_code == 200, c.text
    assert c.json()["onboarding_step"] == "COMPLETED"
    assert c.json()["onboarding_completed"] is True

    db: Session = SessionFactory()
    try:
        user = db.query(User).filter(User.email == "flow.user@example.com").one()
        assert user.onboarding_step == "COMPLETED"
        assert bool(user.onboarding_completed) is True
    finally:
        db.close()


def test_onboarding_state_machine_rejects_skips(client_and_session) -> None:
    client, _ = client_and_session
    reg = _register_user(client, email="skip.user@example.com")
    token = reg["access_token"]

    skip = client.post(
        "/onboarding/complete",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert skip.status_code == 400
    assert "Invalid onboarding transition" in skip.text

    p = client.post(
        "/onboarding/preferences",
        json={"genres": ["Pop"], "artists": []},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert p.status_code == 200, p.text

    repeat = client.post(
        "/onboarding/preferences",
        json={"genres": ["Pop"], "artists": []},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert repeat.status_code == 200, repeat.text


def test_onboarding_state_machine_reentrant_endpoints(client_and_session) -> None:
    client, _ = client_and_session
    reg = _register_user(client, email="reentrant.user@example.com")
    token = reg["access_token"]

    p1 = client.post(
        "/onboarding/preferences",
        json={"genres": ["House"], "artists": ["Artist A"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert p1.status_code == 200, p1.text
    assert p1.json()["onboarding_step"] == "COMPLETED"

    p2 = client.post(
        "/onboarding/preferences",
        json={"genres": ["House"], "artists": ["Artist A"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert p2.status_code == 200, p2.text
    assert p2.json()["onboarding_step"] == "COMPLETED"

    s1 = client.post("/discovery/first-session", headers={"Authorization": f"Bearer {token}"})
    assert s1.status_code == 200, s1.text
    s2 = client.post("/discovery/first-session", headers={"Authorization": f"Bearer {token}"})
    assert s2.status_code == 200, s2.text

    c1 = client.post("/onboarding/complete", headers={"Authorization": f"Bearer {token}"})
    assert c1.status_code == 200, c1.text
    assert c1.json()["onboarding_step"] == "COMPLETED"
    c2 = client.post("/onboarding/complete", headers={"Authorization": f"Bearer {token}"})
    assert c2.status_code == 200, c2.text
    assert c2.json()["onboarding_step"] == "COMPLETED"

    p3 = client.post(
        "/onboarding/preferences",
        json={"genres": ["Ambient"], "artists": []},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert p3.status_code == 200, p3.text
    assert p3.json()["onboarding_step"] == "COMPLETED"
