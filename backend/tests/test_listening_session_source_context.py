"""ListeningSession source_type / source_id on start-session and stream paths."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.artist import Artist
from app.models.listening_session import ListeningSession
from app.models.song import SONG_STATE_DRAFT, Song
from app.models.user import User
from app.services.listening_checkpoint_service import process_start_listening_session
from app.services.stream_service import StreamService


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    db = TestSession()
    try:
        u = User(email="ls.source@test.example", username="ls_source_user")
        db.add(u)
        db.flush()
        a = Artist(slug="ls-source-artist", name="LS Source", owner_user_id=u.id)
        db.add(a)
        db.flush()
        song = Song(
            slug="ls-source-song",
            title="Track",
            artist_id=a.id,
            upload_status="ready",
            state=SONG_STATE_DRAFT,
            duration_seconds=180,
        )
        db.add(song)
        db.commit()
        yield db
    finally:
        db.close()


def test_start_session_without_source_context(db_session: Session) -> None:
    uid = int(db_session.query(User.id).scalar())
    sid = int(db_session.query(Song.id).scalar())
    out = process_start_listening_session(
        db_session, user_id=uid, song_id=sid
    )
    ls = (
        db_session.query(ListeningSession)
        .filter(ListeningSession.id == int(out["session_id"]))
        .one()
    )
    assert ls.source_type == "direct"
    assert ls.source_id is None


@patch("app.services.stream_service.queue.enqueue", lambda *args, **kwargs: None)
def test_process_stream_implicit_session_defaults_source_direct(db_session: Session) -> None:
    uid = int(db_session.query(User.id).scalar())
    song_id = int(db_session.query(Song.id).scalar())
    svc = StreamService()
    out = svc.process_stream(
        db_session,
        user_id=uid,
        song_id=song_id,
        duration=45,
        listening_session_id=None,
        idempotency_key="test-implicit-session-src",
    )
    assert out["status"] == "ok"
    sid = int(out["listening_session_id"])
    ls = db_session.query(ListeningSession).filter(ListeningSession.id == sid).one()
    assert ls.source_type == "direct"
    assert ls.source_id is None


def test_start_session_with_source_context(db_session: Session) -> None:
    uid = int(db_session.query(User.id).scalar())
    song_id = int(db_session.query(Song.id).scalar())
    out = process_start_listening_session(
        db_session,
        user_id=uid,
        song_id=song_id,
        source_type="discovery",
        source_id="disc-req-abc",
    )
    ls = (
        db_session.query(ListeningSession)
        .filter(ListeningSession.id == int(out["session_id"]))
        .one()
    )
    assert ls.source_type == "discovery"
    assert ls.source_id == "disc-req-abc"


def test_start_session_rejects_source_id_without_type(db_session: Session) -> None:
    uid = int(db_session.query(User.id).scalar())
    song_id = int(db_session.query(Song.id).scalar())
    with pytest.raises(HTTPException) as exc:
        process_start_listening_session(
            db_session,
            user_id=uid,
            song_id=song_id,
            source_id="orphan",
        )
    assert exc.value.status_code == 400


def test_start_session_rejects_invalid_source_type(db_session: Session) -> None:
    uid = int(db_session.query(User.id).scalar())
    song_id = int(db_session.query(Song.id).scalar())
    with pytest.raises(HTTPException) as exc:
        process_start_listening_session(
            db_session,
            user_id=uid,
            song_id=song_id,
            source_type="radio",
        )
    assert exc.value.status_code == 400


def test_start_session_source_type_only_allowed(db_session: Session) -> None:
    uid = int(db_session.query(User.id).scalar())
    song_id = int(db_session.query(Song.id).scalar())
    out = process_start_listening_session(
        db_session,
        user_id=uid,
        song_id=song_id,
        source_type="direct",
        source_id=None,
    )
    ls = (
        db_session.query(ListeningSession)
        .filter(ListeningSession.id == int(out["session_id"]))
        .one()
    )
    assert ls.source_type == "direct"
    assert ls.source_id is None
