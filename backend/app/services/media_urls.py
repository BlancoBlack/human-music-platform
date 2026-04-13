"""Public URL helpers for uploaded media (shared by catalog and discovery)."""


def public_media_url_from_stored_path(file_path: str | None) -> str | None:
    """Same URL shape as ``cover_url`` / static ``/uploads`` mount in ``GET /songs/{id}``."""
    if file_path is None or not str(file_path).strip():
        return None
    p = str(file_path).replace("\\", "/").lstrip("/")
    return f"/{p}"
