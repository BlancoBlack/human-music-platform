from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.artist import Artist
from app.models.release_participant import (
    RELEASE_PARTICIPANT_APPROVAL_TYPE_FEATURE,
    RELEASE_PARTICIPANT_APPROVAL_TYPE_SPLIT,
    RELEASE_PARTICIPANT_STATUS_ACCEPTED,
    RELEASE_PARTICIPANT_STATUS_PENDING,
    RELEASE_PARTICIPANT_STATUS_REJECTED,
    ReleaseParticipant,
)
from app.models.song import SONG_STATE_READY_FOR_RELEASE, Song
from app.models.song_artist_split import SongArtistSplit
from app.models.song_featured_artist import SongFeaturedArtist
from app.models.user import User
from app.services.release_approval_service import (
    approve_participation,
    compute_release_approval_status,
    is_release_approvable,
    refresh_release_approval_status,
    reject_participation,
)
from app.services.release_service import create_release, publish_release
from app.services.release_participant_service import sync_release_participants
from app.services.release_participant_service import get_release_feature_artist_ids
from app.services.song_artist_split_service import set_splits_for_song


def _sqlite_engine_with_fk(path: str):
    eng = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})

    @event.listens_for(eng, "connect")
    def _fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return eng


class ReleaseApprovalServiceTests(unittest.TestCase):
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
                    User(id=11, email="collab@example.com", onboarding_step="REGISTERED"),
                    User(id=12, email="intruder@example.com", onboarding_step="REGISTERED"),
                ]
            )
            db.add_all(
                [
                    Artist(id=1, name="Primary", payout_method="none", owner_user_id=10),
                    Artist(id=2, name="Split Artist", payout_method="none", owner_user_id=11),
                    Artist(id=3, name="Featured Artist", payout_method="none", owner_user_id=11),
                    Artist(id=4, name="Unrelated Artist", payout_method="none", owner_user_id=10),
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

    def _setup_release_with_song(self, db):
        release = create_release(
            db,
            title="Approval Test Release",
            artist_id=1,
            release_type="single",
            release_date=datetime.utcnow(),
            owner_user_id=10,
        )
        song = Song(
            slug="approval-track",
            title="Approval Track",
            artist_id=1,
            release_id=int(release.id),
            upload_status="ready",
            state=SONG_STATE_READY_FOR_RELEASE,
        )
        db.add(song)
        db.flush()
        db.add_all(
            [
                SongArtistSplit(song_id=int(song.id), artist_id=1, share=0.7, split_bps=7000),
                SongArtistSplit(song_id=int(song.id), artist_id=2, share=0.3, split_bps=3000),
                SongFeaturedArtist(song_id=int(song.id), artist_id=3, position=1),
            ]
        )
        db.commit()
        sync_release_participants(db, int(release.id), commit=True)
        return release, song

    def test_split_blocks_release(self) -> None:
        db = self.Session()
        try:
            release, _song = self._setup_release_with_song(db)
            self.assertFalse(is_release_approvable(db, release_id=int(release.id)))
            self.assertEqual(str(release.approval_status), "pending_approvals")
            with self.assertRaisesRegex(ValueError, "all split participants approve"):
                publish_release(db, release_id=int(release.id))
        finally:
            db.close()

    def test_release_pending_state(self) -> None:
        db = self.Session()
        try:
            release, _song = self._setup_release_with_song(db)
            status = compute_release_approval_status(db, release_id=int(release.id))
            self.assertEqual(status, "pending_approvals")
            release = db.query(type(release)).filter_by(id=int(release.id)).one()
            self.assertEqual(str(release.approval_status), "pending_approvals")
        finally:
            db.close()

    def test_release_ready_state(self) -> None:
        db = self.Session()
        try:
            release, _song = self._setup_release_with_song(db)
            user = db.query(User).filter(User.id == 11).one()
            approve_participation(db, release_id=int(release.id), artist_id=2, user=user)
            release = db.query(type(release)).filter_by(id=int(release.id)).one()
            self.assertEqual(str(release.approval_status), "ready")
        finally:
            db.close()

    def test_feature_rejection_does_not_block(self) -> None:
        db = self.Session()
        try:
            release, song = self._setup_release_with_song(db)
            user = db.query(User).filter(User.id == 11).one()
            approve_participation(db, release_id=int(release.id), artist_id=2, user=user)
            reject_participation(db, release_id=int(release.id), artist_id=3, user=user)
            self.assertTrue(is_release_approvable(db, release_id=int(release.id)))
            remaining = (
                db.query(ReleaseParticipant)
                .filter(
                    ReleaseParticipant.release_id == int(release.id),
                    ReleaseParticipant.artist_id == 3,
                )
                .first()
            )
            self.assertIsNotNone(remaining)
            assert remaining is not None
            self.assertEqual(remaining.status, RELEASE_PARTICIPANT_STATUS_REJECTED)
            featured = (
                db.query(SongFeaturedArtist)
                .filter(
                    SongFeaturedArtist.song_id == int(song.id),
                    SongFeaturedArtist.artist_id == 3,
                )
                .first()
            )
            self.assertIsNotNone(featured)
        finally:
            db.close()

    def test_approve_flow(self) -> None:
        db = self.Session()
        try:
            release, _song = self._setup_release_with_song(db)
            user = db.query(User).filter(User.id == 11).one()
            row = (
                db.query(ReleaseParticipant)
                .filter(
                    ReleaseParticipant.release_id == int(release.id),
                    ReleaseParticipant.artist_id == 2,
                )
                .one()
            )
            self.assertEqual(row.status, RELEASE_PARTICIPANT_STATUS_PENDING)
            self.assertEqual(row.approval_type, RELEASE_PARTICIPANT_APPROVAL_TYPE_SPLIT)
            updated = approve_participation(
                db,
                release_id=int(release.id),
                artist_id=2,
                user=user,
            )
            self.assertEqual(updated.status, RELEASE_PARTICIPANT_STATUS_ACCEPTED)
            self.assertIsNotNone(updated.approved_at)
            self.assertEqual(
                int(updated.approved_split_version or 0),
                int(
                    db.query(type(release))
                    .filter_by(id=int(release.id))
                    .one()
                    .split_version
                ),
            )
            refreshed = db.query(type(release)).filter_by(id=int(release.id)).one()
            self.assertEqual(str(refreshed.approval_status), "ready")
        finally:
            db.close()

    def test_collaborator_can_approve(self) -> None:
        db = self.Session()
        try:
            release, _song = self._setup_release_with_song(db)
            collaborator_user = db.query(User).filter(User.id == 11).one()
            updated = approve_participation(
                db,
                release_id=int(release.id),
                artist_id=2,
                user=collaborator_user,
            )
            self.assertEqual(updated.status, RELEASE_PARTICIPANT_STATUS_ACCEPTED)
        finally:
            db.close()

    def test_reject_flow(self) -> None:
        db = self.Session()
        try:
            release, _song = self._setup_release_with_song(db)
            user = db.query(User).filter(User.id == 11).one()
            reject_participation(db, release_id=int(release.id), artist_id=2, user=user)
            row = (
                db.query(ReleaseParticipant)
                .filter(
                    ReleaseParticipant.release_id == int(release.id),
                    ReleaseParticipant.artist_id == 2,
                )
                .one()
            )
            self.assertEqual(row.status, "rejected")
            self.assertFalse(is_release_approvable(db, release_id=int(release.id)))
            refreshed = db.query(type(release)).filter_by(id=int(release.id)).one()
            self.assertEqual(str(refreshed.approval_status), "pending_approvals")
        finally:
            db.close()

    def test_split_rejection_preserves_feature_context_for_same_artist(self) -> None:
        db = self.Session()
        try:
            release, song = self._setup_release_with_song(db)
            db.add(SongFeaturedArtist(song_id=int(song.id), artist_id=2, position=2))
            db.commit()
            user = db.query(User).filter(User.id == 11).one()
            reject_participation(
                db,
                release_id=int(release.id),
                artist_id=2,
                user=user,
                reason="Not participating",
            )
            featured = (
                db.query(SongFeaturedArtist)
                .filter(
                    SongFeaturedArtist.song_id == int(song.id),
                    SongFeaturedArtist.artist_id == 2,
                )
                .first()
            )
            self.assertIsNotNone(featured)
            feature_context_ids = get_release_feature_artist_ids(db, release_id=int(release.id))
            self.assertIn(2, feature_context_ids)
            participants = sync_release_participants(db, int(release.id), commit=True)
            participant_two = next(
                p for p in participants if int(p.artist_id) == 2
            )
            self.assertTrue(getattr(participant_two, "has_feature_context", False))
        finally:
            db.close()

    def test_state_updates_on_approval(self) -> None:
        db = self.Session()
        try:
            release, _song = self._setup_release_with_song(db)
            release = db.query(type(release)).filter_by(id=int(release.id)).one()
            self.assertEqual(str(release.approval_status), "pending_approvals")
            user = db.query(User).filter(User.id == 11).one()
            approve_participation(db, release_id=int(release.id), artist_id=2, user=user)
            release = db.query(type(release)).filter_by(id=int(release.id)).one()
            self.assertEqual(str(release.approval_status), "ready")
        finally:
            db.close()

    def test_state_updates_on_split_change(self) -> None:
        db = self.Session()
        try:
            release, song = self._setup_release_with_song(db)
            initial_split_version = int(
                db.query(type(release)).filter_by(id=int(release.id)).one().split_version
            )
            user = db.query(User).filter(User.id == 11).one()
            approve_participation(db, release_id=int(release.id), artist_id=2, user=user)
            release = db.query(type(release)).filter_by(id=int(release.id)).one()
            self.assertEqual(str(release.approval_status), "ready")
            row_before = (
                db.query(ReleaseParticipant)
                .filter(
                    ReleaseParticipant.release_id == int(release.id),
                    ReleaseParticipant.artist_id == 2,
                )
                .one()
            )
            approved_version = int(row_before.approved_split_version or 0)
            self.assertGreater(approved_version, 0)
            set_splits_for_song(
                db,
                int(song.id),
                [
                    {"artist_id": 1, "share": 0.5},
                    {"artist_id": 2, "share": 0.3},
                    {"artist_id": 4, "share": 0.2},
                ],
            )
            release = db.query(type(release)).filter_by(id=int(release.id)).one()
            self.assertEqual(int(release.split_version), initial_split_version + 1)
            self.assertEqual(str(release.approval_status), "pending_approvals")
            row_after = (
                db.query(ReleaseParticipant)
                .filter(
                    ReleaseParticipant.release_id == int(release.id),
                    ReleaseParticipant.artist_id == 2,
                )
                .one()
            )
            self.assertEqual(row_after.status, RELEASE_PARTICIPANT_STATUS_PENDING)
            self.assertIsNone(row_after.approved_at)
            self.assertIsNone(row_after.approved_split_version)
            row = (
                db.query(ReleaseParticipant)
                .filter(
                    ReleaseParticipant.release_id == int(release.id),
                    ReleaseParticipant.artist_id == 4,
                )
                .first()
            )
            self.assertIsNotNone(row)
        finally:
            db.close()

    def test_approval_remains_when_splits_do_not_change(self) -> None:
        db = self.Session()
        try:
            release, _song = self._setup_release_with_song(db)
            user = db.query(User).filter(User.id == 11).one()
            approve_participation(db, release_id=int(release.id), artist_id=2, user=user)
            sync_release_participants(db, int(release.id), commit=True)
            row = (
                db.query(ReleaseParticipant)
                .filter(
                    ReleaseParticipant.release_id == int(release.id),
                    ReleaseParticipant.artist_id == 2,
                )
                .one()
            )
            self.assertEqual(row.status, RELEASE_PARTICIPANT_STATUS_ACCEPTED)
            self.assertIsNotNone(row.approved_at)
            self.assertIsNotNone(row.approved_split_version)
        finally:
            db.close()

    def test_split_change_invalidates_only_split_approval_participants(self) -> None:
        db = self.Session()
        try:
            release, song = self._setup_release_with_song(db)
            user = db.query(User).filter(User.id == 11).one()
            approve_participation(db, release_id=int(release.id), artist_id=2, user=user)
            approve_participation(db, release_id=int(release.id), artist_id=3, user=user)
            release = db.query(type(release)).filter_by(id=int(release.id)).one()
            self.assertEqual(str(release.approval_status), "ready")
            set_splits_for_song(
                db,
                int(song.id),
                [
                    {"artist_id": 1, "share": 0.8},
                    {"artist_id": 2, "share": 0.2},
                ],
            )
            split_row = (
                db.query(ReleaseParticipant)
                .filter(
                    ReleaseParticipant.release_id == int(release.id),
                    ReleaseParticipant.artist_id == 2,
                )
                .one()
            )
            feature_row = (
                db.query(ReleaseParticipant)
                .filter(
                    ReleaseParticipant.release_id == int(release.id),
                    ReleaseParticipant.artist_id == 3,
                )
                .one()
            )
            self.assertEqual(split_row.status, RELEASE_PARTICIPANT_STATUS_PENDING)
            self.assertEqual(feature_row.status, RELEASE_PARTICIPANT_STATUS_ACCEPTED)
            self.assertIsNotNone(feature_row.approved_at)
            self.assertEqual(feature_row.approval_type, RELEASE_PARTICIPANT_APPROVAL_TYPE_FEATURE)
        finally:
            db.close()

    def test_non_owner_cannot_approve(self) -> None:
        db = self.Session()
        try:
            release, _song = self._setup_release_with_song(db)
            intruder = db.query(User).filter(User.id == 12).one()
            with self.assertRaises(PermissionError):
                approve_participation(
                    db,
                    release_id=int(release.id),
                    artist_id=2,
                    user=intruder,
                )
        finally:
            db.close()

    def test_owner_cannot_approve_others(self) -> None:
        db = self.Session()
        try:
            release, _song = self._setup_release_with_song(db)
            owner_user = db.query(User).filter(User.id == 10).one()
            with self.assertRaises(PermissionError):
                approve_participation(
                    db,
                    release_id=int(release.id),
                    artist_id=2,
                    user=owner_user,
                )
        finally:
            db.close()

    def test_sync_preserves_status_and_approved_at(self) -> None:
        db = self.Session()
        try:
            release, _song = self._setup_release_with_song(db)
            row = (
                db.query(ReleaseParticipant)
                .filter(
                    ReleaseParticipant.release_id == int(release.id),
                    ReleaseParticipant.artist_id == 2,
                )
                .one()
            )
            ts = datetime.utcnow()
            release_row = db.query(type(release)).filter_by(id=int(release.id)).one()
            current_split_version = int(release_row.split_version)
            row.status = RELEASE_PARTICIPANT_STATUS_ACCEPTED
            row.approved_at = ts
            row.approved_split_version = current_split_version
            db.add(row)
            db.commit()

            sync_release_participants(db, int(release.id), commit=True)
            reloaded = (
                db.query(ReleaseParticipant)
                .filter(
                    ReleaseParticipant.release_id == int(release.id),
                    ReleaseParticipant.artist_id == 2,
                )
                .one()
            )
            self.assertEqual(reloaded.status, RELEASE_PARTICIPANT_STATUS_ACCEPTED)
            self.assertEqual(reloaded.approved_at, ts)
        finally:
            db.close()

    def test_feature_participant_has_feature_approval_type(self) -> None:
        db = self.Session()
        try:
            release, _song = self._setup_release_with_song(db)
            row = (
                db.query(ReleaseParticipant)
                .filter(
                    ReleaseParticipant.release_id == int(release.id),
                    ReleaseParticipant.artist_id == 3,
                )
                .one()
            )
            self.assertEqual(row.approval_type, RELEASE_PARTICIPANT_APPROVAL_TYPE_FEATURE)
            self.assertTrue(row.requires_approval)
        finally:
            db.close()

    def test_rejection_reason_saved(self) -> None:
        db = self.Session()
        try:
            release, _song = self._setup_release_with_song(db)
            user = db.query(User).filter(User.id == 11).one()
            reject_participation(
                db,
                release_id=int(release.id),
                artist_id=2,
                user=user,
                reason="Split terms are not acceptable",
            )
            row = (
                db.query(ReleaseParticipant)
                .filter(
                    ReleaseParticipant.release_id == int(release.id),
                    ReleaseParticipant.artist_id == 2,
                )
                .one()
            )
            self.assertEqual(row.rejection_reason, "Split terms are not acceptable")
        finally:
            db.close()

    def test_non_participant_cannot_act(self) -> None:
        db = self.Session()
        try:
            release, _song = self._setup_release_with_song(db)
            owner_user = db.query(User).filter(User.id == 10).one()
            with self.assertRaises(ValueError):
                approve_participation(
                    db,
                    release_id=int(release.id),
                    artist_id=4,
                    user=owner_user,
                )
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
