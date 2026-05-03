"""Discovery global like signal loader and scoring integration."""

from __future__ import annotations

import math
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.artist import Artist
from app.models.like_event import LikeEvent
from app.models.song import SONG_STATE_DRAFT, Song
from app.models.song_media_asset import SONG_MEDIA_KIND_MASTER_AUDIO, SongMediaAsset
from app.models.user import User
from app.services.discovery_ranking import load_like_signal_by_song, score_candidates
from app.services.signal_aggregator import LIKE_MATURITY_MINUTES
from app.services.signal_aggregator import LIKE_BOOST_ALPHA, LIKE_CAP, compute_signal_contributions


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
        u = User(email="like-sig@test.example", username="like_sig_user")
        db.add(u)
        db.flush()
        a = Artist(slug="like-sig-artist", name="LS", owner_user_id=u.id)
        db.add(a)
        db.flush()
        base_ts = datetime(2025, 6, 1, 12, 0, 0)
        songs: list[Song] = []
        for i in range(3):
            s = Song(
                slug=f"like-sig-song-{i}",
                title=f"S{i}",
                artist_id=a.id,
                upload_status="ready",
                state=SONG_STATE_DRAFT,
                created_at=base_ts,
            )
            db.add(s)
            songs.append(s)
        db.flush()
        for s in songs:
            db.add(
                SongMediaAsset(
                    song_id=int(s.id),
                    kind=SONG_MEDIA_KIND_MASTER_AUDIO,
                    file_path=f"/tmp/{s.slug}.wav",
                    mime_type="audio/wav",
                    byte_size=100,
                    sha256="b" * 64,
                )
            )
        db.commit()
        yield db
    finally:
        db.close()


def test_load_like_signal_by_song_respects_cutoff(db_session: Session) -> None:
    s0 = db_session.query(Song).filter_by(slug="like-sig-song-0").one()
    s1 = db_session.query(Song).filter_by(slug="like-sig-song-1").one()
    u = db_session.query(User).filter_by(username="like_sig_user").one()
    anchor = datetime(2025, 6, 15, 12, 0, 0)
    cutoff = anchor - timedelta(days=14)
    db_session.add_all(
        [
            LikeEvent(user_id=u.id, song_id=int(s0.id), created_at=anchor - timedelta(days=1)),
            LikeEvent(user_id=u.id, song_id=int(s1.id), created_at=anchor - timedelta(days=20)),
        ]
    )
    db_session.commit()
    mature_upper = anchor - timedelta(minutes=int(LIKE_MATURITY_MINUTES))
    out = load_like_signal_by_song(
        db_session,
        [int(s0.id), int(s1.id)],
        cutoff=cutoff,
        mature_upper=mature_upper,
    )
    assert out.get(int(s0.id)) == 1
    assert int(s1.id) not in out


def test_load_like_signal_excludes_immature_likes(db_session: Session) -> None:
    s0 = db_session.query(Song).filter_by(slug="like-sig-song-0").one()
    u = db_session.query(User).filter_by(username="like_sig_user").one()
    anchor = datetime(2025, 6, 15, 12, 0, 0)
    cutoff = anchor - timedelta(days=14)
    mature_upper = anchor - timedelta(minutes=int(LIKE_MATURITY_MINUTES))
    db_session.add(
        LikeEvent(user_id=u.id, song_id=int(s0.id), created_at=anchor - timedelta(minutes=5))
    )
    db_session.commit()
    out = load_like_signal_by_song(
        db_session,
        [int(s0.id)],
        cutoff=cutoff,
        mature_upper=mature_upper,
    )
    assert out.get(int(s0.id), 0) == 0


def test_score_delta_from_like_boost_only(db_session: Session) -> None:
    """Same inputs except like map: score/for_you increase by like_boost only."""
    s0 = db_session.query(Song).filter_by(slug="like-sig-song-0").one()
    sid = int(s0.id)
    pop = {sid: 10.0}
    rel = {sid: 0.0}
    artists = {sid: 1}
    days = {sid: 30}
    listened: set[int] = set()

    scored_no = score_candidates(
        [sid],
        pop,
        rel,
        artists,
        days,
        listened,
        None,
        playlist_count_by_song={sid: 0},
        reorder_signal_by_song={},
        like_count_by_song={},
    )
    scored_yes = score_candidates(
        [sid],
        pop,
        rel,
        artists,
        days,
        listened,
        None,
        playlist_count_by_song={sid: 0},
        reorder_signal_by_song={},
        like_count_by_song={sid: 10},
    )
    r0 = scored_no[0]
    r1 = scored_yes[0]
    lb = float(r1["like_boost"])
    assert r1["playlist_boost"] == pytest.approx(r0["playlist_boost"])
    assert r1["reorder_boost"] == pytest.approx(r0["reorder_boost"])
    assert float(r1["score"]) - float(r0["score"]) == pytest.approx(lb)
    assert float(r1["for_you_score"]) - float(r0["for_you_score"]) == pytest.approx(lb)
    expected_sig = math.log1p(min(10, LIKE_CAP))
    assert float(r1["like_signal"]) == pytest.approx(expected_sig)
    assert float(r1["like_boost"]) == pytest.approx(LIKE_BOOST_ALPHA * expected_sig)


def test_like_count_zero_matches_log1p_zero() -> None:
    s = compute_signal_contributions(0, 0.0, like_count=0)
    assert s["global"]["likes"]["raw"] == 0
    assert s["global"]["likes"]["signal"] == pytest.approx(0.0)
    assert s["global"]["likes"]["boost"] == pytest.approx(0.0)
