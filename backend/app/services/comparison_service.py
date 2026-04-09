from app.core.database import SessionLocal
from app.economics_constants import ARTIST_SHARE
from app.models.song import Song
from app.models.user_balance import UserBalance
from app.services.payout_service import calculate_user_distribution
from app.services.pool_payout_service import calculate_global_distribution


def compare_models(user_id: int) -> dict:
    """
    Compare user-centric vs global pool distributions for the given user.

    Returns a deterministic structure without triggering any payout execution.
    """

    db = SessionLocal()

    try:
        user_balance = db.query(UserBalance).filter_by(user_id=user_id).first()
        if not user_balance:
            return []

        # Same artist-pool base as calculate_user_distribution / global pool (ARTIST_SHARE).
        user_artist_pool = float(user_balance.monthly_amount) * ARTIST_SHARE

        user_distribution = calculate_user_distribution(user_id)
        pool_distribution = calculate_global_distribution()

        all_song_ids_raw = set()
        for entry in user_distribution:
            song_id = entry.get("song_id")
            if song_id is not None:
                all_song_ids_raw.add(int(song_id))
        for entry in pool_distribution:
            song_id = entry.get("song_id")
            if song_id is not None:
                all_song_ids_raw.add(int(song_id))

        if all_song_ids_raw:
            song_rows = (
                db.query(Song.id, Song.is_system)
                .filter(Song.id.in_(sorted(all_song_ids_raw)))
                .all()
            )
            system_song_ids = {int(song_id) for song_id, is_system in song_rows if bool(is_system)}
        else:
            system_song_ids = set()

        user_distribution = [
            e for e in user_distribution
            if e.get("song_id") is not None and int(e["song_id"]) not in system_song_ids
        ]
        pool_distribution = [
            e for e in pool_distribution
            if e.get("song_id") is not None and int(e["song_id"]) not in system_song_ids
        ]

        user_by_song = {e["song_id"]: e for e in user_distribution}
        pool_by_song = {e["song_id"]: e for e in pool_distribution}

        all_song_ids = sorted(set(user_by_song.keys()) | set(pool_by_song.keys()))

        comparison = []
        for song_id in all_song_ids:
            u = user_by_song.get(song_id)
            p = pool_by_song.get(song_id)

            pool_share = p.get("share") if p else None
            pool_amount = (
                round(pool_share * user_artist_pool, 2)
                if pool_share is not None
                else None
            )

            comparison.append(
                {
                    "song_id": song_id,
                    "user_share": u.get("share") if u else None,
                    "user_payout": u.get("payout") if u else None,
                    "pool_share": pool_share,
                    "pool_amount": pool_amount,
                }
            )

        return {
            "user_id": user_id,
            "comparison": comparison,
        }
    finally:
        db.close()

