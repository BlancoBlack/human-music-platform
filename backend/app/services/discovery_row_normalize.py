"""
Strict JSON shape for discovery track rows (Step 4 output).

Idempotent normalization: safe to call more than once.
"""

from __future__ import annotations

UNKNOWN_TRACK = "Unknown track"
UNKNOWN_ARTIST = "Unknown artist"


def _strict_public_url(value: object) -> str | None:
    """Return a non-empty public URL string, or ``None`` (never ``\"\"`` or whitespace)."""
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


def normalize_discovery_track_row(row: dict) -> dict:
    """
    Enforce strict response types and null policy for ``audio_url`` / ``cover_url``.

    - ``playable`` is always a Python ``bool``; if false, ``audio_url`` is forced to ``None``.
    - ``title`` / ``artist_name`` are non-empty strings (fallbacks applied).
    - ``id`` is ``int``.
    """
    try:
        sid = int(row["id"])
    except (KeyError, TypeError, ValueError):
        sid = 0

    raw_title = row.get("title")
    title = (str(raw_title).strip() if raw_title is not None else "") or UNKNOWN_TRACK

    raw_artist = row.get("artist_name")
    artist_name = (str(raw_artist).strip() if raw_artist is not None else "") or UNKNOWN_ARTIST

    pl = row.get("playable")
    if isinstance(pl, bool):
        playable = pl
    elif isinstance(pl, int):
        playable = pl != 0
    elif isinstance(pl, str):
        playable = pl.strip().lower() in ("true", "1", "yes")
    else:
        playable = bool(pl)

    audio_url = _strict_public_url(row.get("audio_url"))
    cover_url = _strict_public_url(row.get("cover_url"))

    if not playable:
        audio_url = None
    raw_context = row.get("context_tag")
    context_tag = (str(raw_context).strip() if raw_context is not None else "") or None

    return {
        "id": sid,
        "title": title,
        "artist_name": artist_name,
        "audio_url": audio_url,
        "cover_url": cover_url,
        "playable": playable,
        "context_tag": context_tag,
    }


def normalize_discovery_sections_response(
    sections: dict[str, list[dict]],
) -> dict[str, list[dict]]:
    """
    Lightweight final pass: normalize every row in every section (no raises).

    Section order is the source of truth. Hydration must never reorder items.
    """
    order = ("play_now", "for_you", "explore", "curated")
    out: dict[str, list[dict]] = {}
    for key in order:
        rows = sections.get(key) or []
        out[key] = [normalize_discovery_track_row(dict(r)) for r in rows]
    return out
