"""
Application-layer invariants for ``SongArtistSplit`` (no DB schema changes).

Used before persisting splits so invalid configurations never reach the database.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence, Union

# Float tolerance for SUM(share) == 1.0 (binary float noise)
SHARE_SUM_TOLERANCE = 1e-6


class SplitValidationError(ValueError):
    """Raised when a song's split set violates financial invariants."""


def validate_song_splits(
    splits: Sequence[Union[Mapping[str, Any], Any]],
) -> None:
    """
    Validate a complete split set for one song (replace semantics).

    Expects each row to be a mapping with ``artist_id`` and ``share``, or an
    object with those attributes (e.g. ``SongArtistSplit``).

    Invariants:
    - At least one split.
    - ``artist_id`` is never NULL.
    - ``share`` in (0, 1].
    - No duplicate ``artist_id``.
    - Sum of ``share`` equals 1.0 within ``SHARE_SUM_TOLERANCE``.
    """
    if not splits:
        raise SplitValidationError(
            "At least one split is required per song; received an empty list."
        )

    seen_artist_ids: set[int] = set()
    total_share = 0.0

    for index, row in enumerate(splits):
        if isinstance(row, Mapping):
            artist_id = row.get("artist_id")
            share = row.get("share")
        else:
            artist_id = getattr(row, "artist_id", None)
            share = getattr(row, "share", None)

        if artist_id is None:
            raise SplitValidationError(
                f"Split at index {index}: artist_id cannot be null."
            )

        if not isinstance(artist_id, int):
            try:
                artist_id = int(artist_id)  # type: ignore[arg-type]
            except (TypeError, ValueError) as exc:
                raise SplitValidationError(
                    f"Split at index {index}: artist_id must be an integer."
                ) from exc

        if share is None:
            raise SplitValidationError(
                f"Split at index {index}: share cannot be null."
            )

        try:
            share_f = float(share)
        except (TypeError, ValueError) as exc:
            raise SplitValidationError(
                f"Split at index {index}: share must be a number."
            ) from exc

        if share_f <= 0 or share_f > 1:
            raise SplitValidationError(
                f"Split at index {index}: share must be in (0, 1]; got {share_f!r}."
            )

        if artist_id in seen_artist_ids:
            raise SplitValidationError(
                f"Duplicate artist_id {artist_id}: each artist may appear at most once per song."
            )
        seen_artist_ids.add(artist_id)
        total_share += share_f

    if abs(total_share - 1.0) > SHARE_SUM_TOLERANCE:
        raise SplitValidationError(
            f"Shares must sum to 1.0 (tolerance {SHARE_SUM_TOLERANCE}); "
            f"got sum={total_share!r}."
        )
