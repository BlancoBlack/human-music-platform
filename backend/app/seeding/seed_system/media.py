from __future__ import annotations

import hashlib

from sqlalchemy.orm import Session

from app.models.artist import Artist
from app.models.song import Song
from app.models.song_artist_split import SongArtistSplit
from app.models.song_credit_entry import SongCreditEntry
from app.models.song_media_asset import (
    SONG_MEDIA_KIND_COVER_ART,
    SONG_MEDIA_KIND_MASTER_AUDIO,
    SongMediaAsset,
)


def ensure_song_credits_splits_and_media(
    db: Session,
    *,
    songs: list[Song],
    artists_by_id: dict[int, Artist],
    master_path: str,
    cover_path: str,
) -> None:
    for song in songs:
        artist = artists_by_id[int(song.artist_id)]
        _ensure_song_credits(db, song=song, artist=artist)
        _ensure_song_split(db, song=song)
        _ensure_song_media(db, song=song, master_path=master_path, cover_path=cover_path)


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


def _ensure_song_split(db: Session, *, song: Song) -> None:
    row = (
        db.query(SongArtistSplit)
        .filter(
            SongArtistSplit.song_id == int(song.id),
            SongArtistSplit.artist_id == int(song.artist_id),
        )
        .one_or_none()
    )
    if row is None:
        db.add(
            SongArtistSplit(
                song_id=int(song.id),
                artist_id=int(song.artist_id),
                share=1.0,
                split_bps=10000,
            )
        )
    else:
        row.share = 1.0
        row.split_bps = 10000


def _ensure_song_media(db: Session, *, song: Song, master_path: str, cover_path: str) -> None:
    for kind, path, mime in (
        (SONG_MEDIA_KIND_MASTER_AUDIO, master_path, "audio/wav"),
        (SONG_MEDIA_KIND_COVER_ART, cover_path, "image/png"),
    ):
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
