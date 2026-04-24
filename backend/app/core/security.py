"""Password hashing (bcrypt via passlib)."""

from __future__ import annotations

from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

_BCRYPT_MAX_PASSWORD_BYTES = 72


def validate_password_for_bcrypt(plain: str) -> None:
    if plain is None:
        raise ValueError("Password is required")
    if len(str(plain).encode("utf-8")) > _BCRYPT_MAX_PASSWORD_BYTES:
        raise ValueError("Password too long")


def hash_password(plain: str) -> str:
    validate_password_for_bcrypt(plain)
    return _pwd_context.hash(plain)


def verify_password(plain: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    return _pwd_context.verify(plain, password_hash)
