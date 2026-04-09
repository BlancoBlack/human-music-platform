"""Tests for song_credit_entries.position (aligned with song_featured_artists.position)."""

from __future__ import annotations

import os
import tempfile
import unittest

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

# Loads Base and registers all ORM models on Base.metadata.
from app.core.database import Base
from app.models.artist import Artist
from app.models.song_credit_entry import SongCreditEntry
from app.services.song_metadata_service import (
    create_song_with_metadata,
    replace_song_credit_entries,
)


def _sqlite_engine_with_fk(path: str):
    eng = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})

    @event.listens_for(eng, "connect")
    def _fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return eng


class SongCreditEntriesPositionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._fd, self._path = tempfile.mkstemp(suffix=".db")
        os.close(self._fd)
        self.engine = _sqlite_engine_with_fk(self._path)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        db = self.Session()
        try:
            db.add(Artist(id=1, name="Primary", payout_method="none"))
            db.commit()
        finally:
            db.close()

    def tearDown(self) -> None:
        self.engine.dispose()
        try:
            os.unlink(self._path)
        except OSError:
            pass

    def test_create_maps_list_order_to_position(self) -> None:
        db = self.Session()
        try:
            song = create_song_with_metadata(
                db,
                title="Album Cut",
                artist_id=1,
                credits=[
                    {"name": "Alpha", "role": "producer"},
                    {"name": "Beta", "role": "mix engineer"},
                    {"name": "Gamma", "role": "musician"},
                ],
            )
            rows = (
                db.query(SongCreditEntry)
                .filter(SongCreditEntry.song_id == song.id)
                .order_by(SongCreditEntry.position)
                .all()
            )
            self.assertEqual(
                [(r.position, r.display_name, r.role) for r in rows],
                [
                    (1, "Alpha", "producer"),
                    (2, "Beta", "mix engineer"),
                    (3, "Gamma", "musician"),
                ],
            )
        finally:
            db.close()

    def test_more_than_20_credits_rejected(self) -> None:
        db = self.Session()
        try:
            credits = [{"name": f"N{i}", "role": "studio"} for i in range(21)]
            with self.assertRaises(ValueError):
                create_song_with_metadata(
                    db, title="T", artist_id=1, credits=credits
                )
        finally:
            db.close()

    def test_replace_rewrites_positions_sequentially(self) -> None:
        db = self.Session()
        try:
            song = create_song_with_metadata(
                db,
                title="T",
                artist_id=1,
                credits=[{"name": "A", "role": "producer"}],
            )
            replace_song_credit_entries(
                db,
                int(song.id),
                [
                    {"name": "Z", "role": "studio"},
                    {"name": "Y", "role": "studio"},
                ],
            )
            db.commit()
            rows = (
                db.query(SongCreditEntry)
                .filter(SongCreditEntry.song_id == song.id)
                .order_by(SongCreditEntry.position)
                .all()
            )
            self.assertEqual([r.display_name for r in rows], ["Z", "Y"])
            self.assertEqual([r.position for r in rows], [1, 2])
        finally:
            db.close()


class SongCreditEntriesSqliteMigrationTests(unittest.TestCase):
    def test_rename_sort_order_to_position_preserves_values(self) -> None:
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            eng = _sqlite_engine_with_fk(path)
            with eng.begin() as conn:
                conn.execute(
                    text(
                        "CREATE TABLE song_credit_entries ("
                        "id INTEGER PRIMARY KEY, song_id INTEGER NOT NULL, "
                        "sort_order INTEGER NOT NULL, display_name VARCHAR(512) NOT NULL, "
                        "role VARCHAR(64) NOT NULL)"
                    )
                )
                conn.execute(
                    text(
                        "INSERT INTO song_credit_entries "
                        "(id, song_id, sort_order, display_name, role) "
                        "VALUES (1, 1, 3, 'X', 'producer')"
                    )
                )
                conn.execute(
                    text(
                        "ALTER TABLE song_credit_entries "
                        "RENAME COLUMN sort_order TO position"
                    )
                )
                row = conn.execute(
                    text("SELECT position, display_name FROM song_credit_entries WHERE id = 1")
                ).fetchone()
            self.assertEqual(row, (3, "X"))
        finally:
            eng.dispose()
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
