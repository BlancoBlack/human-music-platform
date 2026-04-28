from __future__ import annotations

import hashlib

from sqlalchemy.orm import Session

from app.models.artist import Artist
from app.models.release_media_asset import (
    RELEASE_MEDIA_ASSET_TYPE_COVER_ART,
    ReleaseMediaAsset,
)
from app.models.song import Song
from app.models.song_credit_entry import SongCreditEntry
from app.models.song_media_asset import (
    SONG_MEDIA_KIND_MASTER_AUDIO,
    SongMediaAsset,
)
from app.services.song_artist_split_service import set_splits_for_song


def ensure_song_credits_splits_and_media(
    db: Session,
    *,
    songs: list[Song],
    artists_by_id: dict[int, Artist],
    master_path: str,
    cover_path: str,
) -> None:
    for song in songs:
        if song.release_id is None:
            raise RuntimeError(
                f"Seed lifecycle violation: song {int(song.id)} missing release_id before media stage."
            )
        artist = artists_by_id[int(song.artist_id)]
        _ensure_song_credits(db, song=song, artist=artist)
        set_splits_for_song(
            db,
            int(song.id),
            [{"artist_id": int(song.artist_id), "share": 1.0}],
            commit=False,
        )
        _ensure_song_media(db, song=song, master_path=master_path)
        _ensure_release_cover(db, song=song, cover_path=cover_path)


def _ensure_song_credits(db: Session, *, song: Song, artist: Artist) -> None:
    desired = [
        (1, str(artist.name), "songwriter"),
        (2, "Seed Producer", "producer"),
    ]
    existing = (
        db.query(SongCreditEntry)
        .filter(SongCreditEntry.song_id == int(song.id))
        .order_by(SongCreditEntry.position.asc())
        .all()
    )
    by_pos = {int(entry.position): entry for entry in existing}
    for pos, display_name, role in desired:
        row = by_pos.get(pos)
        if row is None:
            db.add(
                SongCreditEntry(
                    song_id=int(song.id),
                    position=pos,
                    display_name=display_name,
                    role=role,
                )
            )
        else:
            row.display_name = display_name
            row.role = role


def _ensure_song_media(db: Session, *, song: Song, master_path: str) -> None:
    kind = SONG_MEDIA_KIND_MASTER_AUDIO
    path = master_path
    mime = "audio/wav"
    sha = hashlib.sha256(f"{song.id}:{kind}:{path}".encode("utf-8")).hexdigest()
    row = (
        db.query(SongMediaAsset)
        .filter(SongMediaAsset.song_id == int(song.id), SongMediaAsset.kind == kind)
        .one_or_none()
    )
    if row is None:
        db.add(
            SongMediaAsset(
                song_id=int(song.id),
                kind=kind,
                file_path=path,
                mime_type=mime,
                byte_size=2048,
                sha256=sha,
            )
        )
    else:
        row.file_path = path
        row.mime_type = mime
        row.byte_size = 2048
        row.sha256 = sha


def _ensure_release_cover(db: Session, *, song: Song, cover_path: str) -> None:
    if song.release_id is None:
        return
    row = (
        db.query(ReleaseMediaAsset)
        .filter(
            ReleaseMediaAsset.release_id == int(song.release_id),
            ReleaseMediaAsset.asset_type == RELEASE_MEDIA_ASSET_TYPE_COVER_ART,
        )
        .one_or_none()
    )
    if row is None:
        db.add(
            ReleaseMediaAsset(
                release_id=int(song.release_id),
                asset_type=RELEASE_MEDIA_ASSET_TYPE_COVER_ART,
                file_path=str(cover_path),
            )
        )
    else:
        row.file_path = str(cover_path)
