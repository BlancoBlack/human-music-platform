"""Tests for song media upload service (audio + deprecated song-cover write)."""

from __future__ import annotations

import io
import os
import tempfile
import unittest
import wave

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.artist import Artist
from app.models.song import Song
from app.models.song_media_asset import SONG_MEDIA_KIND_MASTER_AUDIO, SongMediaAsset
from app.services import song_media_upload_service as smu
from app.services.song_media_upload_service import (
    MasterAudioImmutableError,
    WavFileTooLargeError,
    build_master_wav_storage_filename,
    compute_pipeline_upload_status,
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


class MasterWavFilenameTests(unittest.TestCase):
    def test_example_shape(self) -> None:
        self.assertEqual(
            build_master_wav_storage_filename(
                song_id=12,
                artist_name="Mina Qiu",
                title="Tu Collar",
            ),
            "song_12__mina-qiu__tu-collar__master.wav",
        )

    def test_special_chars_sanitized(self) -> None:
        name = build_master_wav_storage_filename(
            song_id=1,
            artist_name="Foo!!! Bar",
            title="Bar???",
        )
        self.assertEqual(name, "song_1__foo-bar__bar__master.wav")

    def test_truncation_artist_segment(self) -> None:
        name = build_master_wav_storage_filename(
            song_id=1,
            artist_name="x" * 60,
            title="ab",
        )
        self.assertEqual(name, "song_1__" + "x" * 50 + "__ab__master.wav")


class ComputeUploadStatusTests(unittest.TestCase):
    def test_matrix_audio_and_cover_flag_combinations(self) -> None:
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

    def test_audio_upload_status_and_asset_row(self) -> None:
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
            self.assertEqual(song.file_path, "uploads/songs/song_1__a__t__master.wav")
            ma = (
                db.query(SongMediaAsset)
                .filter_by(song_id=1, kind=SONG_MEDIA_KIND_MASTER_AUDIO)
                .first()
            )
            assert ma is not None
            self.assertEqual(ma.byte_size, len(wav))
            self.assertEqual(len(ma.sha256), 64)
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

if __name__ == "__main__":
    unittest.main()
