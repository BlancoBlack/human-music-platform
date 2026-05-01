from app.core.database import SessionLocal
from sqlalchemy import text

from app.services.payout_aggregation_service import (
    get_artist_payout_history_with_db,
    get_artist_payout_summary_with_db,
)
from app.services.pool_payout_service import calculate_artist_spotify_equivalent


def get_artist_dashboard(artist_id: int):
    db = SessionLocal()

    try:
        # Financial source of truth (V2): payout_lines + settlements for on-chain "paid".
        total_cents = (
            db.execute(
                text(
                    """
                    SELECT COALESCE(SUM(pl.amount_cents), 0)
                    FROM payout_lines pl
                    WHERE pl.artist_id = :artist_id
                    """
                ),
                {"artist_id": artist_id},
            ).scalar()
            or 0
        )
        summary = get_artist_payout_summary_with_db(db, int(artist_id))
        paid_cents = int(summary["paid_cents"])
        accrued_cents = int(summary["accrued_cents"])
        failed_cents = int(summary["failed_cents"])
        pending_cents = int(summary["pending_cents"])

        by_song_rows = db.execute(
            text(
                """
                SELECT pl.song_id, COALESCE(SUM(pl.amount_cents), 0) AS total_cents
                FROM payout_lines pl
                WHERE pl.artist_id = :artist_id
                GROUP BY pl.song_id
                ORDER BY total_cents DESC, pl.song_id ASC
                """
            ),
            {"artist_id": artist_id},
        ).fetchall()

        earnings_per_song = [
            {
                "song_id": int(row.song_id),
                "total": round(int(row.total_cents or 0) / 100.0, 2),
                "paid": round(int(row.total_cents or 0) / 100.0, 2),
                "pending": 0.0,
            }
            for row in by_song_rows
        ]

        top_songs = sorted(
            earnings_per_song,
            key=lambda x: x["total"],
            reverse=True,
        )

        total = round(int(total_cents) / 100.0, 2)
        pending = round(int(pending_cents) / 100.0, 2)
        paid = round(int(paid_cents) / 100.0, 2)
        accrued = round(int(accrued_cents) / 100.0, 2)
        failed = round(int(failed_cents) / 100.0, 2)

        spotify_total = calculate_artist_spotify_equivalent(artist_id)
        difference = round(float(total) - float(spotify_total), 2)

        history_rows = get_artist_payout_history_with_db(db, int(artist_id))
        paid_history = [row for row in history_rows if row["status"] == "paid"][:3]
        last_payouts = [
            {
                "batch_id": int(row["batch_id"]),
                "payout_date": row["date"],
                "amount": round(int(row["amount_cents"] or 0) / 100.0, 2),
            }
            for row in paid_history
        ]

        payout_rows = db.execute(
            text(
                """
                SELECT pl.song_id, pl.amount_cents
                FROM payout_lines pl
                WHERE pl.artist_id = :artist_id
                ORDER BY pl.id ASC
                """
            ),
            {"artist_id": artist_id},
        ).fetchall()

        return {
            "artist_id": artist_id,
            "total": total,
            "paid": paid,
            "accrued": accrued,
            "failed_settlement": failed,
            "pending": pending,
            "spotify_total": spotify_total,
            "difference": difference,
            "earnings_per_song": earnings_per_song,
            "top_songs": top_songs,
            "last_payouts": last_payouts,
            "payouts": [
                {
                    "song_id": int(row.song_id),
                    "amount": round(int(row.amount_cents or 0) / 100.0, 2),
                    "status": "settled",
                }
                for row in payout_rows
            ],
        }

    finally:
        db.close()
