"""HttpOnly refresh-token cookie (browser clients; JSON body still supported)."""

from __future__ import annotations

import os

from fastapi import Response

from app.core.auth_config import REFRESH_TOKEN_EXPIRE

REFRESH_COOKIE_NAME = "hm_refresh_token"
AUTH_REFRESH_COOKIE_PATH = "/auth"


def _cookie_secure() -> bool:
    return (os.getenv("AUTH_COOKIE_SECURE", "") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _cookie_samesite() -> str:
    return "none" if _cookie_secure() else "lax"


def attach_refresh_cookie(response: Response, refresh_token: str) -> None:
    max_age = int(REFRESH_TOKEN_EXPIRE.total_seconds())
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=max_age,
        httponly=True,
        secure=_cookie_secure(),
        samesite=_cookie_samesite(),
        path=AUTH_REFRESH_COOKIE_PATH,
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        REFRESH_COOKIE_NAME,
        path=AUTH_REFRESH_COOKIE_PATH,
    )
