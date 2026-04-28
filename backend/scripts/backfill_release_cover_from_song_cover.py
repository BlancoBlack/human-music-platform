#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_db_path() -> Path:
    return _repo_root() / "backend" / "dev.db"


def _count_releases_with_songs(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        """
        SELECT COUNT(DISTINCT r.id)
        FROM releases r
        JOIN songs s
          ON s.release_id = r.id
         AND s.deleted_at IS NULL
        """
    ).fetchone()
    return int(row[0] or 0)


def _count_releases_already_with_cover(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        """
        SELECT COUNT(DISTINCT r.id)
        FROM releases r
        JOIN songs s
          ON s.release_id = r.id
         AND s.deleted_at IS NULL
        WHERE EXISTS (
          SELECT 1
          FROM release_media_assets rma
          WHERE rma.release_id = r.id
            AND rma.asset_type = 'COVER_ART'
        )
        """
    ).fetchone()
    return int(row[0] or 0)


def _select_backfill_candidates(conn: sqlite3.Connection) -> list[tuple[int, str]]:
    rows = conn.execute(
        """
        SELECT
          r.id AS release_id,
          (
            SELECT sma.file_path
            FROM songs s2
            JOIN song_media_assets sma
              ON sma.song_id = s2.id
             AND sma.kind = 'COVER_ART'
            WHERE s2.release_id = r.id
              AND s2.deleted_at IS NULL
              AND TRIM(COALESCE(sma.file_path, '')) <> ''
            ORDER BY s2.id ASC, sma.id ASC
            LIMIT 1
          ) AS cover_path
        FROM releases r
        WHERE EXISTS (
          SELECT 1
          FROM songs s
          WHERE s.release_id = r.id
            AND s.deleted_at IS NULL
        )
          AND NOT EXISTS (
            SELECT 1
            FROM release_media_assets rma
            WHERE rma.release_id = r.id
              AND rma.asset_type = 'COVER_ART'
          )
          AND EXISTS (
            SELECT 1
            FROM songs s3
            JOIN song_media_assets sma2
              ON sma2.song_id = s3.id
             AND sma2.kind = 'COVER_ART'
            WHERE s3.release_id = r.id
              AND s3.deleted_at IS NULL
              AND TRIM(COALESCE(sma2.file_path, '')) <> ''
          )
        ORDER BY r.id ASC
        """
    ).fetchall()
    return [(int(r[0]), str(r[1])) for r in rows]


def _count_releases_missing_any_cover(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        """
        SELECT COUNT(DISTINCT r.id)
        FROM releases r
        JOIN songs s
          ON s.release_id = r.id
         AND s.deleted_at IS NULL
        WHERE NOT EXISTS (
          SELECT 1
          FROM release_media_assets rma
          WHERE rma.release_id = r.id
            AND rma.asset_type = 'COVER_ART'
        )
          AND NOT EXISTS (
          SELECT 1
          FROM songs s2
          JOIN song_media_assets sma
            ON sma.song_id = s2.id
           AND sma.kind = 'COVER_ART'
          WHERE s2.release_id = r.id
            AND s2.deleted_at IS NULL
            AND TRIM(COALESCE(sma.file_path, '')) <> ''
        )
        """
    ).fetchone()
    return int(row[0] or 0)


def run_backfill(db_path: Path, dry_run: bool) -> int:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        total_with_songs = _count_releases_with_songs(conn)
        already_with_cover = _count_releases_already_with_cover(conn)
        candidates = _select_backfill_candidates(conn)
        missing_any_cover = _count_releases_missing_any_cover(conn)

        print(f"db_path={db_path}")
        print(f"releases_with_songs={total_with_songs}")
        print(f"already_with_release_cover={already_with_cover}")
        print(f"eligible_from_song_cover={len(candidates)}")
        print(f"missing_any_cover_anomaly={missing_any_cover}")

        if dry_run:
            print("dry_run=true (no writes)")
            return 0

        updated = 0
        for release_id, cover_path in candidates:
            conn.execute(
                """
                INSERT INTO release_media_assets (release_id, asset_type, file_path, created_at)
                SELECT ?, 'COVER_ART', ?, CURRENT_TIMESTAMP
                WHERE NOT EXISTS (
                  SELECT 1
                  FROM release_media_assets rma
                  WHERE rma.release_id = ?
                    AND rma.asset_type = 'COVER_ART'
                )
                """,
                (release_id, cover_path, release_id),
            )
            if conn.total_changes > updated:
                updated += 1

        conn.commit()
        skipped = max(0, total_with_songs - already_with_cover - updated)
        print(f"releases_updated={updated}")
        print(f"releases_skipped={skipped}")
        print("status=ok")
        return 0
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill ReleaseMediaAsset(COVER_ART) from legacy song covers."
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=_default_db_path(),
        help="Path to SQLite database (default: backend/dev.db).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report counts and candidates without writing.",
    )
    args = parser.parse_args()
    return run_backfill(db_path=args.db.resolve(), dry_run=bool(args.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())
