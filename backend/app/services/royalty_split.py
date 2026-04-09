from __future__ import annotations

from typing import Dict, List, Tuple


def split_song_cents(
    *, song_cents: int, splits: List[Tuple[int, int]]
) -> List[Tuple[int, int]]:
    """
    Deterministic integer-only basis-points split of royalty cents.

    Inputs
    - song_cents: total amount in cents (>= 0)
    - splits: list of (artist_id, split_bps) where split_bps are basis points.
      Required: sum(split_bps) == 10000, no negative values, no duplicate artist_id.

    Output
    - list of (artist_id, amount_cents) such that sum(amount_cents) == song_cents

    Allocation method
    - exact = song_cents * split_bps / 10000
    - base = floor(exact) implemented as integer division
    - remainder cent distribution:
      sort by remainder (descending), then artist_id (ascending), assign +1 cent
      to the top `leftover` artists until totals match.
    """

    if song_cents < 0:
        raise RuntimeError("song_cents must be >= 0")
    if not splits:
        raise RuntimeError("splits must not be empty")

    seen_artist_ids = set()
    units_by_artist: Dict[int, int] = {}
    base_by_artist: Dict[int, int] = {}
    remainder_by_artist: Dict[int, int] = {}

    total_bps = 0
    for artist_id, split_bps in splits:
        a_id = int(artist_id)
        if a_id in seen_artist_ids:
            raise RuntimeError(f"Duplicate artist_id in splits: {a_id}")
        seen_artist_ids.add(a_id)

        bps = int(split_bps)
        if bps < 0:
            raise RuntimeError("split_bps must be >= 0")

        total_bps += bps

        numerator = song_cents * bps
        base = numerator // 10000
        # Derive remainder explicitly from numerator/base to make the
        # fractional-intent audit-friendly (remainder == numerator - base*10000).
        remainder = numerator - (base * 10000)

        base_by_artist[a_id] = int(base)
        remainder_by_artist[a_id] = int(remainder)
        units_by_artist[a_id] = int(base)

    if total_bps != 10000:
        raise RuntimeError(f"Sum of split_bps must be 10000, got {total_bps}")

    base_sum = sum(units_by_artist.values())
    leftover = song_cents - base_sum
    if leftover < 0:
        raise RuntimeError("Conservation error: negative leftover")
    if leftover == 0:
        out = [(a_id, units_by_artist[a_id]) for a_id in units_by_artist]
        # Keep deterministic output ordering.
        out.sort(key=lambda x: x[0])
        return out

    ranked = sorted(
        ((remainder_by_artist[a_id], a_id) for a_id in units_by_artist),
        key=lambda x: (-x[0], x[1]),
    )

    # leftover is the sum of fractional parts; it is always < number of artists for
    # a valid basis-points split, but we still handle safely.
    n = len(ranked)
    for i in range(leftover):
        _, a_id = ranked[i % n]
        units_by_artist[a_id] += 1

    out = [(a_id, units_by_artist[a_id]) for a_id in units_by_artist]
    out.sort(key=lambda x: x[0])

    out_total = sum(cents for _, cents in out)
    if out_total != song_cents:
        raise RuntimeError("Conservation error: split output sum mismatch")

    return out

