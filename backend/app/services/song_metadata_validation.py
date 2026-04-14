from __future__ import annotations

import re


_ISO_COUNTRY_CODE_RE = re.compile(r"^[A-Z]{2}$")


def validate_genre_subgenre_pair(
    *,
    genre_id: int | None,
    subgenre_id: int | None,
) -> tuple[bool, str | None]:
    """
    Service-level non-blocking validation for song metadata pairing.

    Returns:
        (is_valid, reason)
    """
    if subgenre_id is not None and genre_id is None:
        return False, "subgenre_requires_genre"
    return True, None


def validate_country_code(country_code: str | None) -> tuple[bool, str | None]:
    """
    Service-level non-blocking validation for ISO country code format.

    Accepts NULL/empty for backward compatibility.
    """
    if country_code is None:
        return True, None
    normalized = str(country_code).strip().upper()
    if normalized == "":
        return True, None
    if _ISO_COUNTRY_CODE_RE.match(normalized):
        return True, None
    return False, "invalid_country_code"
