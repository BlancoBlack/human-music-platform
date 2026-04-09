from app.core.database import SessionLocal
from app.economics_constants import ARTIST_SHARE
from app.models.user_balance import UserBalance
from app.models.global_listening_aggregate import GlobalListeningAggregate
from app.services.song_split_distribution import split_song_amount_to_artists


def calculate_global_distribution():
    db = SessionLocal()

    try:
        aggregates = db.query(GlobalListeningAggregate).all()

        total_duration = sum(a.total_duration for a in aggregates)

        if total_duration == 0:
            return []

        balances = db.query(UserBalance).all()
        total_pool = sum(float(b.monthly_amount) * ARTIST_SHARE for b in balances)
        print(f"Total artist pool: {total_pool}")

        distribution = []

        for a in aggregates:
            share = a.total_duration / total_duration
            amount = share * total_pool

            distribution.append({
                "song_id": a.song_id,
                "share": round(share, 4),
                "amount": round(amount, 2),
            })

        return distribution

    finally:
        db.close()


def calculate_artist_spotify_equivalent(artist_id: int) -> float:
    """
    Spotify-style global pool share for one artist: ``calculate_global_distribution``
    per-song amounts, then ``SongArtistSplit`` (no share math duplicated elsewhere).
    """
    global_distribution = calculate_global_distribution()
    db = SessionLocal()
    try:
        total = 0.0
        for entry in global_distribution:
            per_artist = split_song_amount_to_artists(
                db,
                entry["song_id"],
                float(entry["amount"]),
            )
            total += per_artist.get(artist_id, 0.0)
        return round(total, 2)
    finally:
        db.close()

