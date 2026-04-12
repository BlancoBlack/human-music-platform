"""JWT auth: register, login, refresh, logout, /me."""

from __future__ import annotations

import os

# Must be set before app (and auth_config) resolve settings on first request.
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-do-not-use-in-prod!!")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
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


def test_register_login_me_refresh_logout(client_and_session) -> None:
    client, _Session = client_and_session
    r = client.post(
        "/auth/register",
        json={"email": "New.User@Example.com", "password": "password1"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "access_token" in data and "refresh_token" in data
    assert data["token_type"] == "bearer"

    r_me = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {data['access_token']}"},
    )
    assert r_me.status_code == 200, r_me.text
    me = r_me.json()
    assert me["email"] == "new.user@example.com"
    assert me["is_active"] is True
    assert me.get("is_email_verified") is False
    assert "listener" in me["roles"]
    assert me["display_name"] == "new.user"

    r_login = client.post(
        "/auth/login",
        json={"email": "new.user@example.com", "password": "password1"},
    )
    assert r_login.status_code == 200, r_login.text
    tok2 = r_login.json()

    r_bad = client.post(
        "/auth/login",
        json={"email": "new.user@example.com", "password": "wrong"},
    )
    assert r_bad.status_code == 401

    r_ref = client.post(
        "/auth/refresh",
        json={"refresh_token": tok2["refresh_token"]},
    )
    assert r_ref.status_code == 200, r_ref.text
    ref_data = r_ref.json()
    assert ref_data["refresh_token"] != tok2["refresh_token"]
    r_me_ref = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {ref_data['access_token']}"},
    )
    assert r_me_ref.status_code == 200

    r_out = client.post(
        "/auth/logout",
        json={"refresh_token": ref_data["refresh_token"]},
    )
    assert r_out.status_code == 204

    r_ref2 = client.post(
        "/auth/refresh",
        json={"refresh_token": tok2["refresh_token"]},
    )
    assert r_ref2.status_code == 401


def test_refresh_uses_http_only_cookie(client_and_session) -> None:
    """Cookie set on login; refresh with empty JSON still works (browser flow)."""
    client, _ = client_and_session
    r = client.post(
        "/auth/register",
        json={"email": "cookie.user@example.com", "password": "password1"},
    )
    assert r.status_code == 200, r.text
    assert "hm_refresh_token" in r.cookies
    r2 = client.post("/auth/refresh", json={})
    assert r2.status_code == 200, r2.text
    assert "access_token" in r2.json()
    r3 = client.post("/auth/refresh", json={})
    assert r3.status_code == 200, r3.text


def test_refresh_rotation_reuse_fails(client_and_session) -> None:
    """Second refresh with the same refresh JWT must fail (one-time use)."""
    client, _ = client_and_session
    r = client.post(
        "/auth/register",
        json={"email": "rotate@example.com", "password": "password1"},
    )
    assert r.status_code == 200, r.text
    rt0 = r.json()["refresh_token"]
    r1 = client.post("/auth/refresh", json={"refresh_token": rt0})
    assert r1.status_code == 200, r1.text
    rt1 = r1.json()["refresh_token"]
    assert rt1 != rt0
    r_dup = client.post("/auth/refresh", json={"refresh_token": rt0})
    assert r_dup.status_code == 401
    r2 = client.post("/auth/refresh", json={"refresh_token": rt1})
    assert r2.status_code == 200, r2.text


def test_register_duplicate_email(client_and_session) -> None:
    client, _ = client_and_session
    body = {"email": "dup@example.com", "password": "password1"}
    assert client.post("/auth/register", json=body).status_code == 200
    r2 = client.post("/auth/register", json=body)
    assert r2.status_code == 400


def test_me_inactive_forbidden(client_and_session) -> None:
    client, SessionFactory = client_and_session
    r = client.post(
        "/auth/register",
        json={"email": "inactive@example.com", "password": "password1"},
    )
    assert r.status_code == 200
    access = r.json()["access_token"]

    db: Session = SessionFactory()
    try:
        u = db.query(User).filter(User.email == "inactive@example.com").one()
        u.is_active = False
        db.commit()
    finally:
        db.close()

    r_me = client.get("/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert r_me.status_code == 403


def test_dev_impersonation_disabled_without_flags(
    client_and_session, monkeypatch
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ENABLE_DEV_IMPERSONATION", "true")
    client, _ = client_and_session
    r = client.post(
        "/auth/register",
        json={"email": "imp.blocked@example.com", "password": "password1"},
    )
    assert r.status_code == 200, r.text
    tok = r.json()["access_token"]
    r2 = client.post(
        "/auth/dev/impersonate",
        json={"target_user_id": 1},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r2.status_code == 403


def test_dev_impersonation_when_enabled(monkeypatch, client_and_session) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("ENABLE_DEV_IMPERSONATION", "true")
    client, _ = client_and_session
    r1 = client.post(
        "/auth/register",
        json={"email": "actor.imp@example.com", "password": "password1"},
    )
    assert r1.status_code == 200, r1.text
    actor_tok = r1.json()["access_token"]
    actor_me = client.get(
        "/auth/me", headers={"Authorization": f"Bearer {actor_tok}"}
    ).json()
    actor_id = int(actor_me["id"])

    r2 = client.post(
        "/auth/register",
        json={"email": "target.imp@example.com", "password": "password1"},
    )
    assert r2.status_code == 200, r2.text
    target_tok = r2.json()["access_token"]
    target_me = client.get(
        "/auth/me", headers={"Authorization": f"Bearer {target_tok}"}
    ).json()
    target_id = int(target_me["id"])

    r_imp = client.post(
        "/auth/dev/impersonate",
        json={"target_user_id": target_id},
        headers={"Authorization": f"Bearer {actor_tok}"},
    )
    assert r_imp.status_code == 200, r_imp.text
    body = r_imp.json()
    assert body.get("impersonation") is True
    imp_tok = body["access_token"]

    r_me = client.get("/auth/me", headers={"Authorization": f"Bearer {imp_tok}"})
    assert r_me.status_code == 200, r_me.text
    me = r_me.json()
    assert me["email"] == "target.imp@example.com"
    assert me["impersonation"]["actor_id"] == actor_id
    assert me["impersonation"]["actor_email"] == "actor.imp@example.com"


def test_impersonation_blocked_on_payout_method_with_bearer(
    monkeypatch, client_and_session
) -> None:
    """Bearer impersonation JWT must not call payout mutation even with admin_key."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("ENABLE_DEV_IMPERSONATION", "true")
    client, _ = client_and_session
    r1 = client.post(
        "/auth/register",
        json={"email": "payout.actor@example.com", "password": "password1"},
    )
    actor_tok = r1.json()["access_token"]
    r2 = client.post(
        "/auth/register",
        json={"email": "payout.target@example.com", "password": "password1"},
    )
    target_id = client.get(
        "/auth/me", headers={"Authorization": f"Bearer {r2.json()['access_token']}"}
    ).json()["id"]
    imp_tok = client.post(
        "/auth/dev/impersonate",
        json={"target_user_id": target_id},
        headers={"Authorization": f"Bearer {actor_tok}"},
    ).json()["access_token"]

    r_block = client.post(
        "/artist/999999/payout-method?admin_key=x",
        data={
            "payout_method": "none",
            "payout_wallet_address": "",
            "payout_bank_info": "",
        },
        headers={"Authorization": f"Bearer {imp_tok}"},
    )
    assert r_block.status_code == 403


def test_me_unauthenticated(client_and_session) -> None:
    client, _ = client_and_session
    assert client.get("/auth/me").status_code == 401
