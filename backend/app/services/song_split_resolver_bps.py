from __future__ import annotations

from typing import List, Tuple

from sqlalchemy.orm import Session

from app.models.song import Song
from app.models.song_artist_split import SongArtistSplit


def get_song_splits_bps(db: Session, song_id: int) -> List[Tuple[int, int]]:
    """
    Resolve song splits as (artist_id, split_bps) with strict invariants.

    Rules:
    - If split rows exist for song_id:
      - no duplicate artist_ids (defensive)
      - each split_bps in [0, 10000]
      - sum(split_bps) == 10000
      - return sorted by artist_id ASC (deterministic)
      - if any invariant fails: raise RuntimeError (no fallback)
    - If no split rows exist:
      - fallback to (song.artist_id, 10000)
      - if song.artist_id is NULL: raise RuntimeError
    """
    sid = int(song_id)

    rows = (
        db.query(SongArtistSplit.artist_id, SongArtistSplit.split_bps)
        .filter(SongArtistSplit.song_id == sid)
        .order_by(SongArtistSplit.artist_id.asc())
        .all()
    )

    if rows:
        seen = set()
        total = 0
        out: List[Tuple[int, int]] = []

        for artist_id, split_bps in rows:
            aid = int(artist_id)
            if aid in seen:
                raise RuntimeError(f"Duplicate artist_id in splits for song_id={sid}: {aid}")
            seen.add(aid)

            bps = int(split_bps)
            if bps < 0 or bps > 10000:
                raise RuntimeError(
                    f"Invalid split_bps for song_id={sid}, artist_id={aid}: {bps}"
                )

            total += bps
            out.append((aid, bps))

        if total != 10000:
            raise RuntimeError(f"Invalid splits for song_id={sid}: sum(split_bps)={total}, expected 10000")

        # Deterministic ordering guarantee.
        out.sort(key=lambda x: x[0])
        return out

    song = db.query(Song.id, Song.artist_id).filter(Song.id == sid).first()
    if song is None:
        raise RuntimeError(f"Song not found for song_id={sid}")
    if song.artist_id is None:
        raise RuntimeError(f"Song {sid} has no splits and song.artist_id is NULL")

    return [(int(song.artist_id), 10000)]

