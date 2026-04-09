"""Tests for 2-step song media uploads (master audio + cover)."""

from __future__ import annotations

import io
import os
import tempfile
import unittest
import wave

from PIL import Image
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.artist import Artist
from app.models.song import Song
from app.models.song_media_asset import (
    SONG_MEDIA_KIND_COVER_ART,
    SONG_MEDIA_KIND_MASTER_AUDIO,
    SongMediaAsset,
)
from app.services import song_media_upload_service as smu
from app.services.song_media_upload_service import (
    CoverResolutionInvalidError,
    MasterAudioImmutableError,
    WavFileTooLargeError,
    compute_pipeline_upload_status,
    upload_song_cover_art,
    upload_song_master_audio,
)


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


def _valid_cover_png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (1400, 1400), (10, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


class ComputeUploadStatusTests(unittest.TestCase):
    def test_matrix(self) -> None:
        self.assertEqual(
            compute_pipeline_upload_status(has_master_audio=False, has_cover_art=False),
            "draft",
        )
        self.assertEqual(
            compute_pipeline_upload_status(has_master_audio=True, has_cover_art=False),
            "audio_uploaded",
        )
        self.assertEqual(
            compute_pipeline_upload_status(has_master_audio=False, has_cover_art=True),
            "cover_uploaded",
        )
        self.assertEqual(
            compute_pipeline_upload_status(has_master_audio=True, has_cover_art=True),
            "ready",
        )


class SongMediaUploadIntegrationTests(unittest.TestCase):
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
            db.add(Artist(id=1, name="A", payout_method="none"))
            db.add(Song(id=1, artist_id=1, title="T", upload_status="draft"))
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

    def test_audio_then_cover_status_and_assets(self) -> None:
        db = self.Session()
        try:
            wav = _minimal_wav_one_second()
            f = io.BytesIO(wav)
            d = upload_song_master_audio(
                db,
                1,
                f,
                original_filename="m.wav",
                content_type="audio/wav",
            )
            self.assertGreaterEqual(d, 1)
            song = db.query(Song).filter(Song.id == 1).first()
            assert song is not None
            self.assertEqual(song.upload_status, "audio_uploaded")
            self.assertEqual(song.file_path, "uploads/songs/1_master.wav")
            ma = (
                db.query(SongMediaAsset)
                .filter_by(song_id=1, kind=SONG_MEDIA_KIND_MASTER_AUDIO)
                .first()
            )
            assert ma is not None
            self.assertEqual(ma.byte_size, len(wav))
            self.assertEqual(len(ma.sha256), 64)

            png = _valid_cover_png_bytes()
            upload_song_cover_art(
                db,
                1,
                io.BytesIO(png),
                original_filename="c.png",
                content_type="image/png",
            )
            db.refresh(song)
            self.assertEqual(song.upload_status, "ready")
            ca = (
                db.query(SongMediaAsset)
                .filter_by(song_id=1, kind=SONG_MEDIA_KIND_COVER_ART)
                .first()
            )
            assert ca is not None
            self.assertTrue(ca.file_path.endswith("1.png"))
        finally:
            db.close()

    def test_cover_too_small_rejected(self) -> None:
        db = self.Session()
        try:
            buf = io.BytesIO()
            Image.new("RGB", (100, 100), (0, 0, 0)).save(buf, format="PNG")
            tiny = buf.getvalue()
            with self.assertRaises(CoverResolutionInvalidError):
                upload_song_cover_art(
                    db,
                    1,
                    io.BytesIO(tiny),
                    original_filename="c.png",
                    content_type="image/png",
                )
        finally:
            db.close()

    def test_wav_too_large_rejected(self) -> None:
        db = self.Session()
        try:
            old_max = smu._WAV_MAX_BYTES
            smu._WAV_MAX_BYTES = 500
            try:
                wav = _minimal_wav_one_second()
                self.assertGreater(len(wav), 500)
                with self.assertRaises(WavFileTooLargeError):
                    upload_song_master_audio(
                        db,
                        1,
                        io.BytesIO(wav),
                        original_filename="m.wav",
                        content_type="audio/wav",
                    )
            finally:
                smu._WAV_MAX_BYTES = old_max
        finally:
            db.close()

    def test_second_master_audio_rejected(self) -> None:
        db = self.Session()
        try:
            wav = _minimal_wav_one_second()
            upload_song_master_audio(
                db,
                1,
                io.BytesIO(wav),
                original_filename="m.wav",
                content_type="audio/wav",
            )
            with self.assertRaises(MasterAudioImmutableError):
                upload_song_master_audio(
                    db,
                    1,
                    io.BytesIO(wav),
                    original_filename="m2.wav",
                    content_type="audio/wav",
                )
        finally:
            db.close()

    def test_cover_can_be_replaced(self) -> None:
        db = self.Session()
        try:
            wav = _minimal_wav_one_second()
            upload_song_master_audio(
                db,
                1,
                io.BytesIO(wav),
                original_filename="m.wav",
                content_type="audio/wav",
            )
            png1 = _valid_cover_png_bytes()
            upload_song_cover_art(
                db,
                1,
                io.BytesIO(png1),
                original_filename="c1.png",
                content_type="image/png",
            )
            buf = io.BytesIO()
            Image.new("RGB", (1600, 1600), (200, 0, 0)).save(buf, format="PNG")
            png2 = buf.getvalue()
            upload_song_cover_art(
                db,
                1,
                io.BytesIO(png2),
                original_filename="c2.png",
                content_type="image/png",
            )
            ca = (
                db.query(SongMediaAsset)
                .filter_by(song_id=1, kind=SONG_MEDIA_KIND_COVER_ART)
                .first()
            )
            assert ca is not None
            self.assertEqual(ca.byte_size, len(png2))
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
