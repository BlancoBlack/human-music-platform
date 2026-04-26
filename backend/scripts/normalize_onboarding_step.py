#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import text

from app.core.database import SessionLocal


def main() -> None:
    db = SessionLocal()
    try:
        db.execute(
            text(
                "UPDATE users SET onboarding_step = 'COMPLETED' "
                "WHERE onboarding_step = 'completed'"
            )
        )
        db.execute(
            text(
                "UPDATE users SET onboarding_step = 'PREFERENCES_SET' "
                "WHERE onboarding_step = 'GENRES_SELECTED'"
            )
        )
        db.execute(
            text(
                "UPDATE users SET onboarding_step = 'REGISTERED' "
                "WHERE onboarding_step IS NULL"
            )
        )
        db.commit()

        rows = db.execute(
            text(
                "SELECT onboarding_step, COUNT(*) AS n "
                "FROM users GROUP BY onboarding_step ORDER BY n DESC"
            )
        ).fetchall()
        print("onboarding_step distribution:")
        for step, count in rows:
            print(f"  {step}: {count}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
