"""Regression tests for legacy SongIngestionService compatibility."""

from __future__ import annotations

import io
import os
import tempfile
import wave
import unittest

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.artist import Artist
from app.models.song import Song
from app.models.song_media_asset import SONG_MEDIA_KIND_MASTER_AUDIO, SongMediaAsset
from app.services.song_ingestion_service import SongIngestionService


def _sqlite_engine(path: str):
    eng = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})

    @event.listens_for(eng, "connect")
    def _fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return eng


def _minimal_wav_one_second() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(44100)
        wf.writeframes(b"\x00\x00" * 44100)
    return buf.getvalue()


class SongIngestionStatusCompatibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self._fd, self._path = tempfile.mkstemp(suffix=".db")
        os.close(self._fd)
        self._cwd = os.getcwd()
        self._tmp_root = tempfile.mkdtemp()
        os.chdir(self._tmp_root)
        self.engine = _sqlite_engine(self._path)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        db = self.Session()
        try:
            db.add(Artist(id=1, name="Legacy Artist", payout_method="none"))
            db.commit()
        finally:
            db.close()

    def tearDown(self) -> None:
        os.chdir(self._cwd)
        self.engine.dispose()
        try:
            os.unlink(self._path)
        except OSError:
            pass
        import shutil

        shutil.rmtree(self._tmp_root, ignore_errors=True)

    def test_legacy_ingestion_writes_canonical_upload_status(self) -> None:
        db = self.Session()
        try:
            service = SongIngestionService()
            song = service.create_song(
                db=db,
                artist_id=1,
                title="Legacy Upload",
                splits=None,
                file=io.BytesIO(_minimal_wav_one_second()),
                original_filename="legacy.wav",
                content_type="audio/wav",
            )
            db.refresh(song)

            self.assertEqual(song.upload_status, "audio_uploaded")
            self.assertNotIn(song.upload_status, {"uploaded", "published"})
            self.assertIsNotNone(song.release_id)

            reloaded = db.query(Song).filter(Song.id == int(song.id)).first()
            assert reloaded is not None
            self.assertEqual(reloaded.upload_status, "audio_uploaded")

            master_asset = (
                db.query(SongMediaAsset)
                .filter_by(song_id=int(song.id), kind=SONG_MEDIA_KIND_MASTER_AUDIO)
                .first()
            )
            assert master_asset is not None
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
