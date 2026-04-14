"""URL-safe kebab-case slugs for taxonomy and discovery."""

from __future__ import annotations

import re

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(label: str) -> str:
    """
    Lowercase kebab-case from a display name.

    Examples:
        "Hip-hop / Rap" -> "hip-hop-rap"
        "Drum & Bass" -> "drum-and-bass"

    Collapses repeated separators; no leading/trailing dashes; never returns empty
    (uses ``unknown``; pair with ``allocate_unique_slug`` for collisions).
    """
    s = (label or "").strip().lower()
    s = s.replace("&", " and ")
    s = s.replace("/", " ")
    s = _NON_ALNUM.sub("-", s)
    s = re.sub(r"-+", "-", s).strip("-").strip()
    return s if s else "unknown"


def allocate_unique_slug(base: str, used: set[str]) -> str:
    """Reserve ``base`` or ``base-2``, ``base-3``, … in ``used``."""
    slug = base
    n = 2
    while slug in used:
        slug = f"{base}-{n}"
        n += 1
    used.add(slug)
    return slug
