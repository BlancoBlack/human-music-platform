"""
Map a song-level monetary amount to per-artist amounts using ``SongArtistSplit``.

Single source of truth for split rules (aligned with ``generate_payouts``).
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.song import Song
from app.models.song_artist_split import SongArtistSplit

logger = logging.getLogger(__name__)

# Float tolerance: assigned total must match ``song_amount`` (after multiplication by shares).
_AMOUNT_ASSIGN_TOLERANCE = 1e-6
_AMOUNT_ASSIGN_TOLERANCE_REL = 1e-9


def split_song_amount_to_artists(
    db: Session,
    song_id: int,
    song_amount: float,
) -> dict[int, float]:
    """
    Distribute ``song_amount`` across artists for ``song_id``.

    Returns ``artist_id -> amount`` (empty only when ``song_amount`` is 0 and nothing
    was assignable, or when ``song_amount`` is 0).

    If ``song_amount > 0`` and the stored configuration cannot assign the full amount,
    raises immediately (fail-fast).

    # CRITICAL:
    # This function is part of the financial core of the system.
    # It MUST NEVER silently lose or reassign money.
    # Any inconsistency must raise immediately.
    """
    song = db.query(Song).filter_by(id=song_id).first()
    splits: list[SongArtistSplit] = []
    if not song:
        out: dict[int, float] = {}
    else:
        splits = db.query(SongArtistSplit).filter_by(song_id=song.id).all()

        if not splits:
            if not song.artist_id:
                out = {}
            else:
                out = {song.artist_id: float(song_amount)}
        else:
            out = {}
            for split in splits:
                if not split.artist_id:
                    continue
                aid = split.artist_id
                out[aid] = out.get(aid, 0.0) + float(song_amount) * float(split.share or 0)

    _enforce_split_output_integrity(
        song_id=song_id,
        song_amount=float(song_amount),
        result=out,
        song=song,
        splits_rows=splits,
    )
    return out


def _enforce_split_output_integrity(
    song_id: int,
    song_amount: float,
    result: dict[int, float],
    *,
    song: Song | None,
    splits_rows: list[SongArtistSplit],
) -> None:
    """
    Fail-fast checks: no silent loss when money should move.
    Does not modify data or normalize amounts.
    """
    if song_amount > 0 and not result:
        logger.debug(
            "split_song_amount_to_artists integrity: empty assignment "
            "(song_id=%s song_amount=%s song_present=%s splits_count=%s)",
            song_id,
            song_amount,
            song is not None,
            len(splits_rows),
        )
        raise Exception("Invalid split configuration: no artists assigned")

    total_assigned = sum(result.values())
    tol = max(
        _AMOUNT_ASSIGN_TOLERANCE,
        _AMOUNT_ASSIGN_TOLERANCE_REL * abs(song_amount),
    )
    if abs(total_assigned - song_amount) > tol:
        logger.debug(
            "split_song_amount_to_artists integrity: total mismatch "
            "(song_id=%s song_amount=%s total_assigned=%s tol=%s result=%s "
            "splits_debug=%s)",
            song_id,
            song_amount,
            total_assigned,
            tol,
            result,
            [
                (getattr(s, "id", None), s.artist_id, s.share)
                for s in splits_rows
            ],
        )
        raise Exception("Split shares do not sum to 1.0")
