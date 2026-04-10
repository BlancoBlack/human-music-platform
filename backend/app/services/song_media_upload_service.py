from __future__ import annotations

import hashlib
import io
import logging
import os
import re
import unicodedata
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.models.artist import Artist
from app.models.song import Song
from app.models.song_media_asset import (
    SONG_MEDIA_KIND_COVER_ART,
    SONG_MEDIA_KIND_MASTER_AUDIO,
    SongMediaAsset,
)
from app.services.song_ingestion_service import (
    _read_upload_bytes,
    _validate_wav_bytes,
    _validate_wav_content_type,
    _validate_wav_filename,
)

logger = logging.getLogger(__name__)

_WAV_MAX_BYTES = 225 * 1024 * 1024
_COVER_MIN_PX = 1400
_COVER_MAX_PX = 3000

# Human-readable segment in stored master WAV name only; song id is authoritative.
_MASTER_FILENAME_SEGMENT_MAX_LEN = 50


def _ascii_fold(text: str) -> str:
    nfd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfd if not unicodedata.combining(c))


def _segment_slug_for_master_filename(raw: str | None, *, max_len: int) -> str:
    """
    Lowercase slug for debug-friendly filenames: spaces -> hyphen, strip specials.
    Not used for identity or lookups.
    """
    if raw is None:
        return "unknown"
    s = _ascii_fold(str(raw).strip())
    if not s:
        return "unknown"
    s = s.lower()
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"[^a-z0-9\-]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    if not s:
        return "unknown"
    if len(s) > max_len:
        s = s[:max_len].rstrip("-")
    return s or "unknown"


def build_master_wav_storage_filename(
    *,
    song_id: int,
    artist_name: str | None,
    title: str | None,
) -> str:
    """
    Disk name only: ``song_{id}__{artist}__{title}__master.wav``.
    Retrieval uses DB ``file_path``; this string is not parsed for logic.
    """
    artist_part = _segment_slug_for_master_filename(
        artist_name, max_len=_MASTER_FILENAME_SEGMENT_MAX_LEN
    )
    title_part = _segment_slug_for_master_filename(
        title, max_len=_MASTER_FILENAME_SEGMENT_MAX_LEN
    )
    return f"song_{int(song_id)}__{artist_part}__{title_part}__master.wav"


class WavFileTooLargeError(ValueError):
    """Maps to HTTP 400 ``{"error": "wav_file_too_large"}``."""


class CoverResolutionInvalidError(ValueError):
    """Maps to HTTP 400 ``{"error": "cover_resolution_invalid"}``."""


class MasterAudioImmutableError(ValueError):
    """Maps to HTTP 400 ``{"error": "master_audio_immutable"}``."""


_COVER_MIME_TO_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
}
_ALLOWED_COVER_MIME = frozenset(_COVER_MIME_TO_EXT.keys())


def bytes_sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compute_pipeline_upload_status(*, has_master_audio: bool, has_cover_art: bool) -> str:
    if has_master_audio and has_cover_art:
        return "ready"
    if has_master_audio:
        return "audio_uploaded"
    if has_cover_art:
        return "cover_uploaded"
    return "draft"


def _kinds_for_song(db: Session, song_id: int) -> set[str]:
    rows = (
        db.query(SongMediaAsset.kind)
        .filter(SongMediaAsset.song_id == int(song_id))
        .all()
    )
    return {str(r[0]) for r in rows}


def _master_audio_asset_exists(db: Session, song_id: int) -> bool:
    return (
        db.query(SongMediaAsset.id)
        .filter(
            SongMediaAsset.song_id == int(song_id),
            SongMediaAsset.kind == SONG_MEDIA_KIND_MASTER_AUDIO,
        )
        .first()
        is not None
    )


def apply_upload_status_from_assets(db: Session, song: Song) -> None:
    kinds = _kinds_for_song(db, int(song.id))
    song.upload_status = compute_pipeline_upload_status(
        has_master_audio=SONG_MEDIA_KIND_MASTER_AUDIO in kinds,
        has_cover_art=SONG_MEDIA_KIND_COVER_ART in kinds,
    )


def _upsert_asset(
    db: Session,
    *,
    song_id: int,
    kind: str,
    file_path: str,
    mime_type: str,
    byte_size: int,
    sha256_hex: str,
    original_filename: str | None,
) -> None:
    row = (
        db.query(SongMediaAsset)
        .filter(
            SongMediaAsset.song_id == int(song_id),
            SongMediaAsset.kind == kind,
        )
        .first()
    )
    if row:
        row.file_path = file_path
        row.mime_type = mime_type
        row.byte_size = byte_size
        row.sha256 = sha256_hex
        row.original_filename = original_filename
    else:
        db.add(
            SongMediaAsset(
                song_id=int(song_id),
                kind=kind,
                file_path=file_path,
                mime_type=mime_type,
                byte_size=byte_size,
                sha256=sha256_hex,
                original_filename=original_filename,
            )
        )


def _normalize_cover_mime(content_type: str | None, original_filename: str | None) -> str:
    if content_type is not None:
        s = str(content_type).split(";", 1)[0].strip().lower()
        if s == "image/jpg":
            s = "image/jpeg"
        if s in _ALLOWED_COVER_MIME:
            return s
    fn = (original_filename or "").lower().strip()
    if fn.endswith(".png"):
        return "image/png"
    if fn.endswith(".jpg") or fn.endswith(".jpeg"):
        return "image/jpeg"
    raise ValueError("Cover must be image/jpeg or image/png (Content-Type or .jpg/.jpeg/.png filename).")


def _sniff_image_mime(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) >= 3 and data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    return None


def _validate_cover_dimensions_and_rgb(data: bytes) -> None:
    """
    Enforce cover resolution bounds and that the image can be decoded as RGB.
    Original bytes are not modified; any conversion is in-memory only.
    """
    try:
        with Image.open(io.BytesIO(data)) as im:
            im.load()
            w, h = im.size
            if (
                w < _COVER_MIN_PX
                or h < _COVER_MIN_PX
                or w > _COVER_MAX_PX
                or h > _COVER_MAX_PX
            ):
                raise CoverResolutionInvalidError(
                    "Invalid cover resolution (must be 1400–3000px square or larger)"
                )
            try:
                rgb = im.convert("RGB")
                rgb.load()
            except Exception as exc:
                raise ValueError(
                    "Cover image must be RGB-compatible (e.g. standard JPEG/PNG)."
                ) from exc
    except CoverResolutionInvalidError:
        raise
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("Could not read cover image for validation.") from exc


def upload_song_master_audio(
    db: Session,
    song_id: int,
    file: Any,
    *,
    original_filename: str | None,
    content_type: str | None,
) -> int:
    song = db.query(Song).filter(Song.id == int(song_id)).first()
    if song is None:
        raise ValueError(f"Song {song_id} not found.")

    _validate_wav_filename(original_filename)
    _validate_wav_content_type(content_type)

    if _master_audio_asset_exists(db, int(song_id)):
        logger.warning(
            "audio_upload_rejected_immutable",
            extra={"song_id": int(song_id)},
        )
        raise MasterAudioImmutableError(
            "Master audio already uploaded and cannot be replaced"
        )

    data = _read_upload_bytes(file)
    if len(data) > _WAV_MAX_BYTES:
        raise WavFileTooLargeError("WAV file too large (max 225MB)")

    duration_seconds = _validate_wav_bytes(data)
    digest = bytes_sha256_hex(data)
    size = len(data)

    artist_row = (
        db.query(Artist.name)
        .filter(Artist.id == int(song.artist_id))
        .first()
    )
    artist_name = str(artist_row[0]) if artist_row else None
    wav_name = build_master_wav_storage_filename(
        song_id=int(song_id),
        artist_name=artist_name,
        title=song.title,
    )
    rel = Path("uploads") / "songs" / wav_name
    os.makedirs(rel.parent, exist_ok=True)
    rel.write_bytes(data)
    rel_str = rel.as_posix()

    song.file_path = rel_str
    song.duration_seconds = int(duration_seconds)

    stored_mime = "audio/wav"
    _upsert_asset(
        db,
        song_id=int(song_id),
        kind=SONG_MEDIA_KIND_MASTER_AUDIO,
        file_path=rel_str,
        mime_type=stored_mime,
        byte_size=size,
        sha256_hex=digest,
        original_filename=original_filename,
    )
    db.flush()
    apply_upload_status_from_assets(db, song)
    db.add(song)
    logger.info(
        "song_audio_uploaded",
        extra={
            "song_id": int(song_id),
            "duration_seconds": int(duration_seconds),
            "file_size": size,
            "sha256": digest,
        },
    )
    db.commit()
    db.refresh(song)
    return int(duration_seconds)


def upload_song_cover_art(
    db: Session,
    song_id: int,
    file: Any,
    *,
    original_filename: str | None,
    content_type: str | None,
) -> None:
    song = db.query(Song).filter(Song.id == int(song_id)).first()
    if song is None:
        raise ValueError(f"Song {song_id} not found.")

    mime = _normalize_cover_mime(content_type, original_filename)
    data = _read_upload_bytes(file)
    sniffed = _sniff_image_mime(data)
    if sniffed is None:
        raise ValueError("File is not a valid JPEG or PNG image.")
    if sniffed != mime:
        raise ValueError("Image bytes do not match declared type (JPEG vs PNG).")

    _validate_cover_dimensions_and_rgb(data)

    digest = bytes_sha256_hex(data)
    size = len(data)
    ext = _COVER_MIME_TO_EXT[mime]

    rel = Path("uploads") / "covers" / f"{int(song_id)}{ext}"
    os.makedirs(rel.parent, exist_ok=True)
    rel.write_bytes(data)
    rel_str = rel.as_posix()

    _upsert_asset(
        db,
        song_id=int(song_id),
        kind=SONG_MEDIA_KIND_COVER_ART,
        file_path=rel_str,
        mime_type=mime,
        byte_size=size,
        sha256_hex=digest,
        original_filename=original_filename,
    )
    db.flush()
    apply_upload_status_from_assets(db, song)
    db.add(song)
    logger.info(
        "song_cover_uploaded",
        extra={
            "song_id": int(song_id),
            "file_size": size,
            "sha256": digest,
        },
    )
    db.commit()
    db.refresh(song)
