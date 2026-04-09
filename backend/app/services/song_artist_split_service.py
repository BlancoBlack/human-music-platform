"""
Create / replace ``SongArtistSplit`` rows for a song with strict validation.

All writes go through :func:`set_splits_for_song` so invariants are enforced
before commit.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_FLOOR
from typing import Any, Mapping, Sequence

from sqlalchemy.orm import Session

from app.models.song import Song
from app.models.song_artist_split import SongArtistSplit
from app.services.song_split_validation import SplitValidationError, validate_song_splits


def _allocate_split_bps_from_shares(
    splits: Sequence[Mapping[str, Any]],
) -> dict[int, int]:
    """
    Deterministically allocate split_bps that sum to exactly 10000 using
    base+largest-remainder on share*10000.

    Remainder sort:
    1) remainder DESC
    2) artist_id ASC
    """
    items: list[tuple[int, Decimal]] = []
    for row in splits:
        aid = int(row["artist_id"])
        # Use Decimal(str(x)) to reduce float representation drift across environments.
        share_d = Decimal(str(row["share"]))
        items.append((aid, share_d))

    # base + remainder in bps space
    base_by_artist: dict[int, int] = {}
    rem_by_artist: dict[int, Decimal] = {}

    assigned = 0
    for aid, share_d in items:
        numerator = share_d * Decimal(10000)
        base_bps = int(numerator.to_integral_value(rounding=ROUND_FLOOR))
        remainder = numerator - Decimal(base_bps)
        if base_bps < 0:
            raise SplitValidationError(f"Invalid base_bps for artist_id={aid}: {base_bps}")
        base_by_artist[aid] = base_bps
        rem_by_artist[aid] = remainder
        assigned += base_bps

    leftover = 10000 - assigned
    if leftover < 0:
        raise SplitValidationError(f"Split bps over-allocation: assigned={assigned} > 10000")

    ranked = sorted(
        ((rem_by_artist[aid], aid) for aid in base_by_artist),
        key=lambda x: (-x[0], x[1]),
    )
    n = len(ranked)
    for i in range(leftover):
        _rem, aid = ranked[i % n]
        base_by_artist[aid] += 1

    total = sum(base_by_artist.values())
    if total != 10000:
        raise SplitValidationError(f"Split bps must sum to 10000; got sum={total}.")

    # Range check
    for aid, bps in base_by_artist.items():
        if bps < 0 or bps > 10000:
            raise SplitValidationError(f"Invalid split_bps for artist_id={aid}: {bps}")

    return base_by_artist


def set_splits_for_song(
    db: Session,
    song_id: int,
    splits: Sequence[Mapping[str, Any]],
) -> list[SongArtistSplit]:
    """
    Replace all splits for ``song_id`` with ``splits`` (validated, then saved).

    ``splits`` is a sequence of dict-like rows: ``{"artist_id": int, "share": float}``.

    Raises:
        SplitValidationError: If invariants fail.
        ValueError: If the song does not exist.
    """
    validate_song_splits(splits)

    song = db.query(Song).filter_by(id=song_id).first()
    if not song:
        raise ValueError(f"Song {song_id} not found.")

    # Enforce strict bps invariants for finance-grade payouts.
    bps_by_artist = _allocate_split_bps_from_shares(splits)

    db.query(SongArtistSplit).filter(SongArtistSplit.song_id == song_id).delete(
        synchronize_session=False
    )

    created: list[SongArtistSplit] = []
    for row in splits:
        artist_id = int(row["artist_id"])
        share = float(row["share"])
        split_bps = int(bps_by_artist[artist_id])
        entity = SongArtistSplit(
            song_id=song_id,
            artist_id=artist_id,
            share=share,
            split_bps=split_bps,
        )
        db.add(entity)
        created.append(entity)

    db.commit()
    for entity in created:
        db.refresh(entity)
    return created
