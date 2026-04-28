"""Release participant sync invariants."""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.artist import Artist
from app.models.song import SONG_STATE_DRAFT, Song
from app.models.song_artist_split import SongArtistSplit
from app.models.song_featured_artist import SongFeaturedArtist
from app.models.user import User
from app.models.release_participant import RELEASE_PARTICIPANT_STATUS_ACCEPTED
from app.models.release_participant import RELEASE_PARTICIPANT_APPROVAL_TYPE_SPLIT
from app.models.release_participant import ReleaseParticipant
from app.models.release import Release
from app.services.release_participant_service import sync_release_participants
from app.services.release_service import create_release
from app.services.song_artist_split_service import set_splits_for_song
from app.services.song_metadata_service import create_song_with_metadata, replace_song_featured_artists


def _sqlite_engine_with_fk(path: str):
    eng = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})

    @event.listens_for(eng, "connect")
    def _fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return eng


class ReleaseParticipantSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self._fd, self._path = tempfile.mkstemp(suffix=".db")
        os.close(self._fd)
        self.engine = _sqlite_engine_with_fk(self._path)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        db = self.Session()
        try:
            db.add_all(
                [
                    User(id=10, email="owner@example.com", onboarding_step="REGISTERED"),
                    User(id=11, email="other@example.com", onboarding_step="REGISTERED"),
                ]
            )
            db.add_all(
                [
                    Artist(id=1, name="Owner", payout_method="none", owner_user_id=10),
                    Artist(id=2, name="Writer", payout_method="none", owner_user_id=11),
                    Artist(id=3, name="Featured", payout_method="none"),
                ]
            )
            db.commit()
        finally:
            db.close()

    def tearDown(self) -> None:
        self.engine.dispose()
        try:
            os.unlink(self._path)
        except OSError:
            pass

    def _participants(self, db, release_id: int) -> list[ReleaseParticipant]:
        return (
            db.query(ReleaseParticipant)
            .filter(ReleaseParticipant.release_id == int(release_id))
            .order_by(ReleaseParticipant.artist_id.asc())
            .all()
        )

    def test_create_song_initializes_participants(self) -> None:
        db = self.Session()
        try:
            song = create_song_with_metadata(db, title="Track 1", artist_id=1)
            assert song.release_id is not None
            rows = self._participants(db, int(song.release_id))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].artist_id, 1)
            self.assertEqual(rows[0].role, "primary")
            self.assertEqual(rows[0].status, "accepted")
        finally:
            db.close()

    def test_splits_sync_creates_missing_primary_participant(self) -> None:
        db = self.Session()
        try:
            song = create_song_with_metadata(db, title="Track 2", artist_id=1)
            assert song.release_id is not None
            set_splits_for_song(
                db,
                int(song.id),
                [{"artist_id": 1, "share": 0.7}, {"artist_id": 2, "share": 0.3}],
            )
            rows = self._participants(db, int(song.release_id))
            self.assertEqual(
                [(r.artist_id, r.role, r.status) for r in rows],
                [
                    (1, "primary", "accepted"),
                    (2, "collaborator", "pending"),
                ],
            )
        finally:
            db.close()

    def test_featured_sync_creates_pending_featured_participant(self) -> None:
        db = self.Session()
        try:
            song = create_song_with_metadata(db, title="Track 3", artist_id=1)
            assert song.release_id is not None
            set_splits_for_song(
                db,
                int(song.id),
                [{"artist_id": 1, "share": 0.8}, {"artist_id": 2, "share": 0.2}],
            )
            replace_song_featured_artists(db, int(song.id), 1, [2, 3])
            db.commit()
            rows = self._participants(db, int(song.release_id))
            self.assertEqual(
                [(r.artist_id, r.role, r.status) for r in rows],
                [
                    (1, "primary", "accepted"),
                    (2, "collaborator", "pending"),
                    (3, "featured", "pending"),
                ],
            )
        finally:
            db.close()

    def test_release_creation_adds_owner_participant(self) -> None:
        db = self.Session()
        try:
            release = create_release(
                db,
                title="Draft Release",
                artist_id=1,
                release_type="single",
                release_date=datetime.utcnow(),
                owner_user_id=10,
            )
            rows = self._participants(db, int(release.id))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].artist_id, 1)
            self.assertEqual(rows[0].status, "accepted")
        finally:
            db.close()

    def test_sync_is_idempotent_and_deduplicated(self) -> None:
        db = self.Session()
        try:
            song = create_song_with_metadata(
                db,
                title="Track 4",
                artist_id=1,
                featured_artist_ids=[3],
            )
            assert song.release_id is not None
            set_splits_for_song(
                db,
                int(song.id),
                [{"artist_id": 1, "share": 0.5}, {"artist_id": 3, "share": 0.5}],
            )
            first = self._participants(db, int(song.release_id))
            set_splits_for_song(
                db,
                int(song.id),
                [{"artist_id": 1, "share": 0.5}, {"artist_id": 3, "share": 0.5}],
            )
            second = self._participants(db, int(song.release_id))
            self.assertEqual(len(first), 2)
            self.assertEqual(len(second), 2)
            self.assertEqual(
                [(r.artist_id, r.role, r.status) for r in second],
                [
                    (1, "primary", "accepted"),
                    (3, "collaborator", "pending"),
                ],
            )
            split_feature_row = (
                db.query(ReleaseParticipant)
                .filter(
                    ReleaseParticipant.release_id == int(song.release_id),
                    ReleaseParticipant.artist_id == 3,
                )
                .one()
            )
            self.assertEqual(split_feature_row.approval_type, RELEASE_PARTICIPANT_APPROVAL_TYPE_SPLIT)
        finally:
            db.close()

    def test_sync_preserves_existing_non_owner_status(self) -> None:
        db = self.Session()
        try:
            song = create_song_with_metadata(db, title="Track 5", artist_id=1)
            assert song.release_id is not None
            set_splits_for_song(
                db,
                int(song.id),
                [{"artist_id": 1, "share": 0.6}, {"artist_id": 2, "share": 0.4}],
            )
            row = (
                db.query(ReleaseParticipant)
                .filter(
                    ReleaseParticipant.release_id == int(song.release_id),
                    ReleaseParticipant.artist_id == 2,
                )
                .one()
            )
            current_split_version = int(
                db.query(Release)
                .filter(Release.id == int(song.release_id))
                .one()
                .split_version
            )
            row.status = RELEASE_PARTICIPANT_STATUS_ACCEPTED
            row.approved_split_version = current_split_version
            db.add(row)
            db.commit()

            sync_release_participants(db, int(song.release_id), commit=True)

            reloaded = (
                db.query(ReleaseParticipant)
                .filter(
                    ReleaseParticipant.release_id == int(song.release_id),
                    ReleaseParticipant.artist_id == 2,
                )
                .one()
            )
            self.assertEqual(reloaded.status, RELEASE_PARTICIPANT_STATUS_ACCEPTED)
            self.assertEqual(reloaded.role, "collaborator")
        finally:
            db.close()

    def test_owner_and_primary_can_differ_owner_remains_accepted(self) -> None:
        db = self.Session()
        try:
            release = create_release(
                db,
                title="Owner vs Primary",
                artist_id=2,
                release_type="single",
                release_date=datetime.utcnow(),
                owner_user_id=10,
            )
            sync_release_participants(db, int(release.id), commit=True)
            rows = self._participants(db, int(release.id))
            self.assertEqual(
                [(r.artist_id, r.role, r.status) for r in rows],
                [
                    (1, "collaborator", "accepted"),
                    (2, "primary", "pending"),
                ],
            )
        finally:
            db.close()

    def test_multi_song_union_collects_all_primary_collaborator_and_featured(self) -> None:
        db = self.Session()
        try:
            release = create_release(
                db,
                title="Compilation",
                artist_id=1,
                release_type="album",
                release_date=datetime.utcnow(),
                owner_user_id=10,
            )
            song_a = Song(
                slug="track-a",
                title="Track A",
                artist_id=1,
                release_id=int(release.id),
                upload_status="draft",
                state=SONG_STATE_DRAFT,
            )
            song_b = Song(
                slug="track-b",
                title="Track B",
                artist_id=2,
                release_id=int(release.id),
                upload_status="draft",
                state=SONG_STATE_DRAFT,
            )
            db.add(song_a)
            db.add(song_b)
            db.flush()
            db.add_all(
                [
                    SongArtistSplit(song_id=int(song_a.id), artist_id=1, share=0.7, split_bps=7000),
                    SongArtistSplit(song_id=int(song_a.id), artist_id=3, share=0.3, split_bps=3000),
                    SongArtistSplit(song_id=int(song_b.id), artist_id=2, share=0.6, split_bps=6000),
                    SongArtistSplit(song_id=int(song_b.id), artist_id=3, share=0.4, split_bps=4000),
                    SongFeaturedArtist(song_id=int(song_a.id), artist_id=2, position=1),
                ]
            )
            db.commit()
            sync_release_participants(db, int(release.id), commit=True)
            rows = self._participants(db, int(release.id))
            self.assertEqual(
                [(r.artist_id, r.role) for r in rows],
                [
                    (1, "primary"),
                    (2, "primary"),
                    (3, "collaborator"),
                ],
            )
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
