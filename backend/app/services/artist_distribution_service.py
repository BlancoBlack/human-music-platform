from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session

from app.models.song import Song
from app.models.song_artist_split import SongArtistSplit
from app.services.royalty_split import split_song_cents


def expand_song_distribution_to_artists(
    db: Session,
    song_distributions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Expand song-level cents into artist-level cents using deterministic integer splits.

    Input row shape (required):
    - song_id
    - cents
    """
    artist_totals: dict[int, dict[str, Any]] = defaultdict(
        lambda: {"cents": 0, "sources": []}
    )
    input_total_cents = 0
    song_ids = [
        int(row["song_id"])
        for row in song_distributions
        if row.get("song_id") is not None
    ]
    split_rows_all = (
        db.query(SongArtistSplit)
        .filter(SongArtistSplit.song_id.in_(song_ids))
        .order_by(SongArtistSplit.song_id.asc(), SongArtistSplit.artist_id.asc())
        .all()
    )
    songs_all = db.query(Song).filter(Song.id.in_(song_ids)).all()
    splits_map: dict[int, list[SongArtistSplit]] = defaultdict(list)
    for split_row in split_rows_all:
        splits_map[int(split_row.song_id)].append(split_row)
    songs_map: dict[int, Song] = {int(song.id): song for song in songs_all}

    for row in song_distributions:
        song_id_raw = row.get("song_id")
        cents_raw = row.get("cents", 0)
        if song_id_raw is None:
            raise RuntimeError("song_id is required in song_distributions rows")

        song_id = int(song_id_raw)
        song_cents = int(cents_raw or 0)
        if song_cents < 0:
            raise RuntimeError("song distribution cents must be >= 0")
        song = songs_map.get(song_id)
        if not song:
            continue

        # Resolve split config for this song.
        split_rows = splits_map.get(song_id, [])
        if not song.artist_id and not split_rows:
            raise ValueError("Song has no artist and no splits")

        input_total_cents += song_cents

        if split_rows:
            splits: list[tuple[int, int]] = [
                (int(r.artist_id), int(r.split_bps or 0)) for r in split_rows
            ]
            split_total_bps = sum(bps for _, bps in splits)
            if split_total_bps != 10000:
                raise RuntimeError(
                    f"Invalid splits for song_id={song_id}: "
                    f"sum(split_bps)={split_total_bps}, expected 10000"
                )
        else:
            splits = [(int(song.artist_id), 10000)]

        per_artist = split_song_cents(song_cents=song_cents, splits=splits)
        for artist_id, cents in per_artist:
            aid = int(artist_id)
            c = int(cents)
            artist_totals[aid]["cents"] += c
            artist_totals[aid]["sources"].append({"song_id": song_id, "cents": c})

    output_total_cents = sum(int(v["cents"]) for v in artist_totals.values())
    if output_total_cents != input_total_cents:
        raise RuntimeError(
            "Conservation error in artist distribution expansion: "
            f"in={input_total_cents}, out={output_total_cents}"
        )

    out: list[dict[str, Any]] = []
    for artist_id in sorted(artist_totals.keys()):
        row = artist_totals[artist_id]
        row_cents = int(row["cents"])
        sources = list(row["sources"])
        sources.sort(key=lambda x: int(x["cents"]), reverse=True)
        sources_total = sum(int(s.get("cents", 0) or 0) for s in sources)
        if sources_total != row_cents:
            raise RuntimeError(
                "Conservation error in artist source composition: "
                f"artist_id={artist_id}, artist_total={row_cents}, sources_total={sources_total}"
            )
        out.append(
            {
                "artist_id": int(artist_id),
                "cents": row_cents,
                "sources": sources,
                "song_count": len(sources),
            }
        )
    return out
