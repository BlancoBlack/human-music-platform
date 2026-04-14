"""Persistence of moods, country_code, and city on song create."""

from __future__ import annotations

import os
import tempfile
import unittest

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.artist import Artist
from app.models.song import Song
from app.models.song_artist_split import SongArtistSplit
from app.services.song_metadata_service import create_song_with_metadata


def _sqlite_engine_with_fk(path: str):
    eng = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})

    @event.listens_for(eng, "connect")
    def _fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return eng


class SongMoodsLocationTests(unittest.TestCase):
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

    def test_create_persists_moods_country_city(self) -> None:
        db = self.Session()
        try:
            song = create_song_with_metadata(
                db,
                title="T1",
                artist_id=1,
                moods=["  dark  ", "bright", ""],
                country_code="es",
                city="  Barcelona  ",
            )
            sid = int(song.id)
            row = db.query(Song).filter(Song.id == sid).one()
            self.assertEqual(row.moods, ["dark", "bright"])
            self.assertEqual(row.country_code, "ES")
            self.assertEqual(row.city, "Barcelona")
        finally:
            db.close()

    def test_create_omits_empty_moods_location(self) -> None:
        db = self.Session()
        try:
            song = create_song_with_metadata(
                db,
                title="T2",
                artist_id=1,
                moods=["", "  "],
                country_code="  ",
                city="",
            )
            sid = int(song.id)
            row = db.query(Song).filter(Song.id == sid).one()
            self.assertIsNone(row.moods)
            self.assertIsNone(row.country_code)
            self.assertIsNone(row.city)
        finally:
            db.close()

    def test_invalid_country_raises(self) -> None:
        db = self.Session()
        try:
            with self.assertRaises(ValueError):
                create_song_with_metadata(
                    db,
                    title="T3",
                    artist_id=1,
                    country_code="ZZZ",
                )
        finally:
            db.close()

    def test_create_inserts_default_primary_split(self) -> None:
        db = self.Session()
        try:
            song = create_song_with_metadata(db, title="SplitSong", artist_id=1)
            sid = int(song.id)
            rows = (
                db.query(SongArtistSplit)
                .filter(SongArtistSplit.song_id == sid)
                .order_by(SongArtistSplit.id.asc())
                .all()
            )
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].artist_id, 1)
            self.assertAlmostEqual(float(rows[0].share), 1.0, places=5)
        finally:
            db.close()
