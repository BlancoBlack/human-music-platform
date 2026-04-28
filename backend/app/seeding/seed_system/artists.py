from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.models.artist import Artist
from app.models.user import User


def upsert_seed_artists(
    db: Session,
    *,
    users: Sequence[User],
    artist_names: Sequence[str],
    wallet_address: str,
) -> list[Artist]:
    if len(users) != len(artist_names):
        raise RuntimeError("Expected one artist per user.")

    artists: list[Artist] = []
    for idx, (user, artist_name) in enumerate(zip(users, artist_names, strict=True), start=1):
        system_key = f"seed.artist.{idx:02d}"
        row = db.query(Artist).filter(Artist.system_key == system_key).one_or_none()
        if row is None:
            row = Artist(
                name=artist_name,
                system_key=system_key,
                owner_user_id=int(user.id),
                payout_method="crypto",
                payout_wallet_address=wallet_address,
                is_system=False,
            )
            db.add(row)
        else:
            row.name = artist_name
            row.owner_user_id = int(user.id)
            row.payout_method = "crypto"
            row.payout_wallet_address = wallet_address
            row.is_system = False
        db.flush()
        artists.append(row)
    return artists
