"""Discovery playlist candidate pool (merge order + labeling + weak playlist score boost)."""

from __future__ import annotations

import math
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.artist import Artist
from app.models.playlist import Playlist, PlaylistTrack
from app.models.song import SONG_STATE_DRAFT, Song
from app.models.song_media_asset import SONG_MEDIA_KIND_MASTER_AUDIO, SongMediaAsset
from app.models.user import User
from app.services.discovery_candidate_pools import get_playlist_candidates
from app.services.discovery_ranking import (
    _PLAYLIST_POPULARITY_ALPHA,
    build_candidate_set,
    load_playlist_membership_counts,
    score_candidates,
)


def _playable_song_row(suffix: int, *, artist_id: int, created_at: datetime) -> tuple[Song, SongMediaAsset]:
    slug = f"dpp-song-{suffix}"
    song = Song(
        slug=slug,
        title=f"T{suffix}",
        artist_id=artist_id,
        upload_status="ready",
        state=SONG_STATE_DRAFT,
        created_at=created_at,
    )
    asset = SongMediaAsset(
        song_id=None,
        kind=SONG_MEDIA_KIND_MASTER_AUDIO,
        file_path=f"/tmp/{slug}.wav",
        mime_type="audio/wav",
        byte_size=100,
        sha256="a" * 64,
    )
    return song, asset


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
        base_ts = datetime(2025, 1, 1)
        u = User(email="dpp@test.example", username="dpp_user")
        db.add(u)
        db.flush()
        a = Artist(slug="dpp-artist", name="DPP", owner_user_id=u.id)
        db.add(a)
        db.flush()
        rows: list[tuple[Song, SongMediaAsset]] = []
        # Songs 1–150 fill low-exposure prefix; 151–153 introduced via playlist merge (same exposure tier).
        for i in range(1, 154):
            song, asset = _playable_song_row(i, artist_id=a.id, created_at=base_ts)
            db.add(song)
            rows.append((song, asset))
        db.flush()
        for song, asset in rows:
            asset.song_id = song.id
            db.add(asset)
        pl = Playlist(
            owner_user_id=u.id,
            title="Mix",
            description=None,
            is_public=True,
            created_at=base_ts,
            updated_at=base_ts,
        )
        db.add(pl)
        db.flush()
        pid = int(pl.id)
        s151 = db.query(Song).filter(Song.slug == "dpp-song-151").one()
        s152 = db.query(Song).filter(Song.slug == "dpp-song-152").one()
        s153 = db.query(Song).filter(Song.slug == "dpp-song-153").one()
        db.add_all(
            [
                PlaylistTrack(playlist_id=pid, song_id=int(s151.id), position=3),
                PlaylistTrack(playlist_id=pid, song_id=int(s152.id), position=1),
                PlaylistTrack(playlist_id=pid, song_id=int(s153.id), position=2),
            ]
        )
        db.commit()
        yield db
    finally:
        db.close()


def test_get_playlist_candidates_orders_playlist_and_caps_three(db_session: Session) -> None:
    out = get_playlist_candidates(db_session, user_id=None)
    assert len(out) == 3
    # position order: song152 pos1, 153 pos2, 151 pos3
    s152 = int(db_session.query(Song.id).filter_by(slug="dpp-song-152").scalar())
    s153 = int(db_session.query(Song.id).filter_by(slug="dpp-song-153").scalar())
    s151 = int(db_session.query(Song.id).filter_by(slug="dpp-song-151").scalar())
    assert out == [s152, s153, s151]


def test_build_candidate_set_playlist_label_after_prefix(db_session: Session) -> None:
    payload = build_candidate_set(db_session, user_id=None)
    labels = payload["candidate_pool_by_song"]
    s151 = int(db_session.query(Song.id).filter_by(slug="dpp-song-151").scalar())
    s152 = int(db_session.query(Song.id).filter_by(slug="dpp-song-152").scalar())
    s153 = int(db_session.query(Song.id).filter_by(slug="dpp-song-153").scalar())
    assert labels.get(s151) == "playlist"
    assert labels.get(s152) == "playlist"
    assert labels.get(s153) == "playlist"
    low_labels = [sid for sid, lb in labels.items() if lb == "low_exposure"]
    assert len(low_labels) >= 1
    assert len(set(payload["candidate_ids"])) == len(payload["candidate_ids"])


def test_build_candidate_set_empty_playlists_no_crash(db_session: Session) -> None:
    db_session.query(PlaylistTrack).delete(synchronize_session=False)
    db_session.query(Playlist).delete(synchronize_session=False)
    db_session.commit()
    payload = build_candidate_set(db_session, user_id=None)
    assert isinstance(payload["candidate_ids"], list)
    assert "candidate_pool_by_song" in payload
    assert payload["playlist_count_by_song"] == {}
    assert payload["reorder_signal_by_song"] == {}
    assert payload.get("like_count_by_song") == {}


def test_load_playlist_membership_counts_public_only(db_session: Session) -> None:
    s151 = int(db_session.query(Song.id).filter_by(slug="dpp-song-151").scalar())
    s152 = int(db_session.query(Song.id).filter_by(slug="dpp-song-152").scalar())
    s153 = int(db_session.query(Song.id).filter_by(slug="dpp-song-153").scalar())
    counts = load_playlist_membership_counts(db_session, [s151, s152, s153])
    assert counts == {s151: 1, s152: 1, s153: 1}


def test_score_candidates_playlist_boost_weak_and_zero_safe(db_session: Session) -> None:
    payload = build_candidate_set(db_session, user_id=None)
    ids = payload["candidate_ids"]
    pop = payload["popularity"]
    rel = payload["relevance"]
    artists = payload["artist_by_song"]
    days = payload["days_since_release"]
    listened = payload["user_listened_artists"]
    truth_counts = payload["playlist_count_by_song"]

    scored_zero = score_candidates(
        ids, pop, rel, artists, days, listened, None, playlist_count_by_song={}
    )
    scored_truth = score_candidates(
        ids, pop, rel, artists, days, listened, None, playlist_count_by_song=truth_counts
    )
    by_id_z = {int(r["song_id"]): r for r in scored_zero}
    by_id_t = {int(r["song_id"]): r for r in scored_truth}
    s151 = int(db_session.query(Song.id).filter_by(slug="dpp-song-151").scalar())
    boost = _PLAYLIST_POPULARITY_ALPHA * math.log1p(1)
    assert float(by_id_t[s151]["score"]) - float(by_id_z[s151]["score"]) == pytest.approx(boost)
    assert float(by_id_t[s151]["for_you_score"]) - float(by_id_z[s151]["for_you_score"]) == pytest.approx(
        boost
    )
    assert int(by_id_z[s151]["playlist_count"]) == 0
    assert float(by_id_z[s151]["playlist_signal"]) == 0.0
    assert float(by_id_z[s151]["reorder_signal"]) == 0.0
    assert float(by_id_z[s151]["reorder_boost"]) == 0.0
    assert int(by_id_t[s151]["playlist_count"]) == 1
    row = by_id_t[s151]
    assert "signals" in row
    assert float(row["signal_score"]) == pytest.approx(
        float(row["user_signal_score"]) + float(row["global_signal_score"])
    )
    assert float(row["global_signal_score"]) == pytest.approx(
        float(row["playlist_boost"]) + float(row["like_boost"])
    )
    assert float(row["playlist_signal"]) == float(row["signals"]["global"]["playlist"]["signal"])
    assert float(row["playlist_boost"]) == float(row["signals"]["global"]["playlist"]["boost"])
    assert float(row["reorder_signal"]) == float(row["signals"]["user"]["reorder"]["signal"])
    assert float(row["reorder_boost"]) == float(row["signals"]["user"]["reorder"]["boost"])
    assert int(row["like_count"]) == int(row["signals"]["global"]["likes"]["raw"])
    assert float(row["like_signal"]) == float(row["signals"]["global"]["likes"]["signal"])
    assert float(row["like_boost"]) == float(row["signals"]["global"]["likes"]["boost"])
    assert float(row["user_signal_score"]) == float(row["signals"]["total"]["user_signal_score"])
    assert float(row["global_signal_score"]) == float(row["signals"]["total"]["global_signal_score"])
    assert float(row["signal_score"]) == pytest.approx(
        float(row["user_signal_score"]) + float(row["global_signal_score"])
    )
