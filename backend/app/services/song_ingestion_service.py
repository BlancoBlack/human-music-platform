from __future__ import annotations

import io
from pathlib import Path
import re
import wave
from typing import Any

from sqlalchemy.orm import Session

from app.models.artist import Artist
from app.models.song import Song
from app.services.release_service import bind_song_to_release, create_single_release_for_song
from app.services.slug_service import ensure_song_slug
from app.services.song_artist_split_service import set_splits_for_song
from app.services.song_state_service import sync_song_state_from_upload_status


_ALLOWED_WAV_CONTENT_TYPES = frozenset(
    {"audio/wav", "audio/x-wav", "audio/wave"}
)

# Shown on upload validation errors so clients know what to export.
_WAV_FORMAT_HINT = "16-bit or 24-bit PCM, 44100 Hz recommended"


def _wav_validation_error(prefix: str) -> ValueError:
    return ValueError(f"{prefix} ({_WAV_FORMAT_HINT})")


def _slugify(text: str) -> str:
    lowered = (text or "").strip().lower()
    spaced = re.sub(r"\s+", "_", lowered)
    cleaned = re.sub(r"[^a-z0-9_]", "", spaced)
    compact = re.sub(r"_+", "_", cleaned).strip("_")
    return compact or "unknown"


def _normalize_content_type(content_type: str | None) -> str | None:
    if content_type is None:
        return None
    s = str(content_type).strip()
    if not s:
        return None
    return s.split(";", 1)[0].strip().lower()


def _validate_wav_content_type(content_type: str | None) -> None:
    """
    When the client sends a Content-Type, enforce WAV-related types.
    Missing or application/octet-stream is allowed (browsers vary); structure is
    still verified via wave.open.
    """
    normalized = _normalize_content_type(content_type)
    if normalized is None:
        return
    if normalized == "application/octet-stream":
        return
    if normalized in _ALLOWED_WAV_CONTENT_TYPES:
        return
    if normalized.startswith("image/") or normalized.startswith("text/"):
        raise _wav_validation_error("Only WAV audio files are allowed")
    raise _wav_validation_error("Only WAV files are allowed (unexpected Content-Type)")


def _validate_wav_filename(original_filename: str | None) -> None:
    if original_filename is None:
        return
    name = str(original_filename).strip()
    if not name:
        return
    if not name.lower().endswith(".wav"):
        raise _wav_validation_error("Only WAV files are allowed")


def _read_upload_bytes(file: Any) -> bytes:
    if file is None:
        raise ValueError("No file provided")
    source = getattr(file, "file", file)
    if source is None:
        raise ValueError("No file provided")
    if not hasattr(source, "read"):
        raise ValueError("No file provided")
    if hasattr(source, "seek"):
        try:
            source.seek(0)
        except OSError:
            pass
    data = source.read()
    if not data:
        raise ValueError("Uploaded file is empty")
    return data


def _validate_wav_bytes(data: bytes) -> int:
    """
    Parse WAV in memory; raises ValueError if not a valid WAV.
    Returns duration in whole seconds (rounded).
    """
    try:
        with wave.open(io.BytesIO(data), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            if rate <= 0 or frames < 0:
                raise _wav_validation_error("Invalid or corrupt WAV file")
            return int(round(float(frames) / float(rate)))
    except wave.Error as exc:
        raise _wav_validation_error("Invalid or corrupt WAV file") from exc
    except ValueError:
        raise
    except Exception as exc:
        raise _wav_validation_error("Invalid or corrupt WAV file") from exc


class SongIngestionService:
    def create_song(
        self,
        db: Session,
        artist_id: int,
        title: str,
        splits: list | None,
        file: Any,
        release_id: int | None = None,
        *,
        original_filename: str | None = None,
        content_type: str | None = None,
    ) -> Song:
        """
        Orchestrates full song creation:
        - validates input
        - creates Song
        - stores file
        - creates splits
        """
        cleaned_title = (title or "").strip()
        if not cleaned_title:
            raise ValueError("title is required.")

        _validate_wav_filename(original_filename)
        _validate_wav_content_type(content_type)

        artist = db.query(Artist).filter(Artist.id == int(artist_id)).first()
        if artist is None:
            raise ValueError(f"Artist {artist_id} not found.")

        audio_bytes = _read_upload_bytes(file)
        duration_seconds = _validate_wav_bytes(audio_bytes)

        song = Song(
            artist_id=int(artist_id),
            title=cleaned_title,
            upload_status="draft",
        )
        sync_song_state_from_upload_status(song)
        db.add(song)
        db.flush()
        ensure_song_slug(db, song, title_source=cleaned_title)
        if release_id is not None:
            bind_song_to_release(db, song=song, release_id=int(release_id))
        else:
            create_single_release_for_song(db, song=song)
        db.commit()
        db.refresh(song)

        uploads_dir = Path("uploads") / "songs"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        artist_slug = _slugify(getattr(artist, "name", ""))
        title_slug = _slugify(cleaned_title)
        filename = f"{artist_slug}__{title_slug}__{int(song.id)}.wav"
        target_path = uploads_dir / filename
        target_path.write_bytes(audio_bytes)

        song.file_path = str(target_path)
        song.upload_status = "uploaded"
        sync_song_state_from_upload_status(song)
        db.add(song)
        db.commit()
        db.refresh(song)

        share_rows = self._resolve_share_rows(
            artist_id=int(artist_id),
            splits=splits,
        )
        set_splits_for_song(
            db=db,
            song_id=int(song.id),
            splits=share_rows,
        )

        song.duration_seconds = duration_seconds
        song.upload_status = "published"
        sync_song_state_from_upload_status(song)
        db.add(song)
        db.commit()
        db.refresh(song)
        return song

    def _resolve_share_rows(self, artist_id: int, splits: list | None) -> list[dict[str, float]]:
        if not splits:
            return [{"artist_id": int(artist_id), "share": 1.0}]

        normalized: list[dict[str, int]] = []
        total_bps = 0
        for row in splits:
            if not isinstance(row, dict):
                raise ValueError("Each split must be an object.")
            if "artist_id" not in row or "split_bps" not in row:
                raise ValueError("Each split must include artist_id and split_bps.")
            aid = int(row["artist_id"])
            bps = int(row["split_bps"])
            if bps < 0 or bps > 10000:
                raise ValueError(f"Invalid split_bps for artist_id={aid}: {bps}")
            normalized.append({"artist_id": aid, "split_bps": bps})
            total_bps += bps

        if total_bps != 10000:
            raise ValueError(f"Split bps must sum to 10000; got {total_bps}.")

        return [
            {
                "artist_id": int(row["artist_id"]),
                "share": float(row["split_bps"]) / 10000.0,
            }
            for row in normalized
        ]
