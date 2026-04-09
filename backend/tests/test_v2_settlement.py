"""V2 settlement: breakdown hash + batch settlement with mocked Algorand."""

from __future__ import annotations

import json
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.artist import Artist
from app.models.payout_batch import PayoutBatch
from app.models.payout_settlement import PayoutSettlement
from app.models.payout_input_snapshot import PayoutInputSnapshot
from app.models.payout_line import PayoutLine
from app.models.snapshot_listening_input import SnapshotListeningInput
from app.models.snapshot_user_pool import SnapshotUserPool
from app.models.song import Song
from app.models.song_artist_split import SongArtistSplit
from app.models.user import User
from app.services.settlement_breakdown import (
    breakdown_totals_match,
    build_payout_breakdown,
    canonical_json_bytes,
    compute_breakdown_hash,
    compute_splits_digest,
)
from app.workers.settlement_worker import process_batch_settlement


@pytest.fixture()
def memory_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    yield db
    db.close()


def test_compute_breakdown_hash_stable():
    payload = {
        "batch_id": 1,
        "songs": [{"cents": 100, "song_id": 2}],
        "total_cents": 100,
    }
    assert compute_breakdown_hash(payload) == compute_breakdown_hash(payload)
    assert len(compute_breakdown_hash(payload)) == 64


def test_compute_splits_digest_stable():
    songs = [
        {"artist_split_bps": 10000, "song_id": 1},
        {"artist_split_bps": 5000, "song_id": 2},
    ]
    assert compute_splits_digest(songs) == compute_splits_digest(list(reversed(songs)))
    assert len(compute_splits_digest(songs)) == 64


def test_breakdown_totals_match():
    assert breakdown_totals_match(
        {"songs": [{"cents": 40}, {"cents": 60}], "total_cents": 100}
    )
    assert not breakdown_totals_match(
        {"songs": [{"cents": 40}, {"cents": 60}], "total_cents": 99}
    )


def test_process_batch_settlement_mock_chain(memory_db):
    db = memory_db
    start = datetime(2025, 1, 1)
    end = datetime(2025, 2, 1)

    artist = Artist(
        name="Payee",
        payout_method="crypto",
        payout_wallet_address="A" * 58,
        is_system=False,
    )
    db.add(artist)
    db.flush()

    user = User(username="u1")
    db.add(user)
    db.flush()

    song = Song(title="Track", artist_id=int(artist.id), is_system=False)
    db.add(song)
    db.flush()

    db.add(
        SongArtistSplit(
            song_id=int(song.id),
            artist_id=int(artist.id),
            share=1.0,
            split_bps=10000,
        )
    )

    batch = PayoutBatch(
        period_start_at=start,
        period_end_at=end,
        status="finalized",
        currency="USD",
        calculation_version="v2",
        antifraud_version="v1",
        snapshot_id=None,
    )
    db.add(batch)
    db.flush()

    snap = PayoutInputSnapshot(
        batch_id=int(batch.id),
        period_start_at=start,
        period_end_at=end,
        currency="USD",
        calculation_version="v2",
        antifraud_version="v1",
        listening_aggregation_version="v1",
        policy_id="v1",
        policy_artist_share=0.7,
        policy_weight_decay_lambda=0.22,
        source_time_cutoff=datetime.utcnow(),
        snapshot_state="sealed",
        sealed_at=datetime.utcnow(),
    )
    db.add(snap)
    db.flush()

    batch.snapshot_id = int(snap.id)
    db.add(batch)
    db.commit()

    db.add(
        SnapshotUserPool(
            snapshot_id=int(snap.id),
            user_id=int(user.id),
            user_pool_cents=10_000,
        )
    )
    db.add(
        SnapshotListeningInput(
            snapshot_id=int(snap.id),
            user_id=int(user.id),
            song_id=int(song.id),
            raw_units_i=5000,
            qualified_units_i=5000,
        )
    )
    db.add(
        PayoutLine(
            batch_id=int(batch.id),
            user_id=int(user.id),
            song_id=int(song.id),
            artist_id=int(artist.id),
            amount_cents=10_000,
            currency="USD",
            line_type="royalty",
            idempotency_key="test:1",
        )
    )
    db.commit()

    class FakeClient:
        def send_asset(self, receiver, amount, asset_id, note=None):
            assert receiver == artist.payout_wallet_address
            assert amount == 10_000 * 10_000
            assert note is not None
            return "FAKE_TX_ABC"

        def wait_for_confirmation(self, tx_id, wait_rounds=0):
            assert tx_id == "FAKE_TX_ABC"
            return {"confirmed-round": 123, "transaction": {"id": tx_id}}

    summary = process_batch_settlement(
        int(batch.id),
        db=db,
        algorand_client_factory=lambda: FakeClient(),
    )
    assert summary["processed"] == 1
    assert summary["confirmed"] == 1
    assert summary["skipped"] == 0

    row = (
        db.query(PayoutSettlement)
        .filter_by(batch_id=int(batch.id), artist_id=int(artist.id))
        .one()
    )
    assert row.execution_status == "confirmed"
    assert row.algorand_tx_id == "FAKE_TX_ABC"
    assert len(row.breakdown_hash) == 64
    assert row.destination_wallet == artist.payout_wallet_address
    assert row.splits_digest and len(row.splits_digest) == 64

    h2 = compute_breakdown_hash(json.loads(row.breakdown_json))
    assert h2 == row.breakdown_hash


def test_resume_submitted_does_not_resend(memory_db):
    """Submitted + tx_id: only wait_for_confirmation; never send_asset again."""
    db = memory_db
    start = datetime(2025, 1, 1)
    end = datetime(2025, 2, 1)

    artist = Artist(
        name="Payee",
        payout_method="crypto",
        payout_wallet_address="B" * 58,
        is_system=False,
    )
    db.add(artist)
    db.flush()

    user = User(username="u2")
    db.add(user)
    db.flush()

    song = Song(title="Track2", artist_id=int(artist.id), is_system=False)
    db.add(song)
    db.flush()

    db.add(
        SongArtistSplit(
            song_id=int(song.id),
            artist_id=int(artist.id),
            share=1.0,
            split_bps=8000,
        )
    )

    batch = PayoutBatch(
        period_start_at=start,
        period_end_at=end,
        status="finalized",
        currency="USD",
        calculation_version="v2",
        antifraud_version="v1",
        snapshot_id=None,
    )
    db.add(batch)
    db.flush()

    snap = PayoutInputSnapshot(
        batch_id=int(batch.id),
        period_start_at=start,
        period_end_at=end,
        currency="USD",
        calculation_version="v2",
        antifraud_version="v1",
        listening_aggregation_version="v1",
        policy_id="v1",
        policy_artist_share=0.7,
        policy_weight_decay_lambda=0.22,
        source_time_cutoff=datetime.utcnow(),
        snapshot_state="sealed",
        sealed_at=datetime.utcnow(),
    )
    db.add(snap)
    db.flush()

    batch.snapshot_id = int(snap.id)
    db.add(batch)
    db.commit()

    db.add(
        SnapshotUserPool(
            snapshot_id=int(snap.id),
            user_id=int(user.id),
            user_pool_cents=5000,
        )
    )
    db.add(
        SnapshotListeningInput(
            snapshot_id=int(snap.id),
            user_id=int(user.id),
            song_id=int(song.id),
            raw_units_i=1000,
            qualified_units_i=1000,
        )
    )
    db.add(
        PayoutLine(
            batch_id=int(batch.id),
            user_id=int(user.id),
            song_id=int(song.id),
            artist_id=int(artist.id),
            amount_cents=5000,
            currency="USD",
            line_type="royalty",
            idempotency_key="test:resume:1",
        )
    )
    db.commit()

    breakdown = build_payout_breakdown(db, int(batch.id), int(artist.id))
    b_json = canonical_json_bytes(breakdown).decode("utf-8")
    b_hash = compute_breakdown_hash(breakdown)
    splits_digest = breakdown.get("splits_digest") or ""

    db.add(
        PayoutSettlement(
            batch_id=int(batch.id),
            artist_id=int(artist.id),
            total_cents=5000,
            breakdown_json=b_json,
            breakdown_hash=b_hash,
            splits_digest=splits_digest,
            destination_wallet=artist.payout_wallet_address,
            algorand_tx_id="ALREADY_SENT_TX",
            execution_status="submitted",
            submitted_at=datetime.utcnow(),
            attempt_count=0,
        )
    )
    db.commit()

    send_calls = []

    class FakeClient:
        def send_asset(self, *args, **kwargs):
            send_calls.append(1)
            raise AssertionError("send_asset must not be called for submitted resume")

        def wait_for_confirmation(self, tx_id, wait_rounds=0):
            assert tx_id == "ALREADY_SENT_TX"
            return {"confirmed-round": 99, "transaction": {"id": tx_id}}

    summary = process_batch_settlement(
        int(batch.id),
        db=db,
        algorand_client_factory=lambda: FakeClient(),
    )
    assert summary["processed"] == 1
    assert summary["confirmed"] == 1
    assert send_calls == []

    row = (
        db.query(PayoutSettlement)
        .filter_by(batch_id=int(batch.id), artist_id=int(artist.id))
        .one()
    )
    assert row.execution_status == "confirmed"
    assert row.algorand_tx_id == "ALREADY_SENT_TX"
