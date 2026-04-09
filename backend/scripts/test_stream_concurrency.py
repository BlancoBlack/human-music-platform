#!/usr/bin/env python3
"""
Concurrent POST /stream smoke test.

Prerequisites:
  - API running from backend/: ./.venv/bin/python -m uvicorn app.main:app (e.g. 127.0.0.1:8000)
  - User X-User-Id exists in DB
  - song_id exists and duration meets validate_listen rules (e.g. 30s)

Does not modify application code.

Example:
  cd backend && ./.venv/bin/python scripts/test_stream_concurrency.py
  ./.venv/bin/python scripts/test_stream_concurrency.py --workers 5 --user-id 2 --song-id 9
"""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def _post_stream(
    url: str,
    user_id: int,
    song_id: int,
    duration: int,
    worker_idx: int,
) -> tuple[int, str, dict | None]:
    jitter_ms = random.uniform(0, 20)
    time.sleep(jitter_ms / 1000.0)

    payload = json.dumps(
        {"song_id": song_id, "duration": duration}
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-User-Id": str(user_id),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            code = resp.status
    except urllib.error.HTTPError as e:
        code = e.code
        body = e.read().decode("utf-8") if e.fp else str(e)
    except urllib.error.URLError as e:
        return -1, str(e), None

    try:
        parsed = json.loads(body) if body.strip() else None
    except json.JSONDecodeError:
        parsed = None
    return code, body, parsed


def _db_recent_count(
    db_path: Path, user_id: int, song_id: int
) -> tuple[int | None, str]:
    if not db_path.is_file():
        return None, f"(skip: no database file at {db_path})"
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT COUNT(*)
                FROM listening_events
                WHERE user_id = ?
                  AND song_id = ?
                  AND datetime(created_at) >= datetime('now', '-1 minute')
                """,
                (user_id, song_id),
            )
            row = cur.fetchone()
            return (int(row[0]) if row else 0), ""
        finally:
            conn.close()
    except sqlite3.Error as e:
        return None, str(e)


def main() -> None:
    parser = argparse.ArgumentParser(description="Concurrent /stream race test")
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="API base URL (no trailing slash)",
    )
    parser.add_argument("--user-id", type=int, default=2, help="X-User-Id header")
    parser.add_argument("--song-id", type=int, default=9, help="JSON song_id")
    parser.add_argument("--duration", type=int, default=30, help="JSON duration (seconds)")
    parser.add_argument(
        "--workers",
        type=int,
        default=5,
        help="Number of parallel requests (2–5 typical)",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Path to SQLite DB (default: backend/test.db next to scripts/)",
    )
    args = parser.parse_args()

    backend_dir = Path(__file__).resolve().parents[1]
    db_path = args.db if args.db is not None else backend_dir / "test.db"

    url = f"{args.base_url.rstrip('/')}/stream"
    n = max(2, min(20, args.workers))

    print(f"POST {url}")
    print(f"X-User-Id: {args.user_id}  body: song_id={args.song_id} duration={args.duration}")
    print(f"Parallel workers: {n}  jitter: 0–20 ms per request")
    print("-" * 60)

    lock = threading.Lock()
    results: list[tuple[int, str, dict | None, int]] = []

    def task(idx: int) -> None:
        code, body, parsed = _post_stream(
            url, args.user_id, args.song_id, args.duration, idx
        )
        with lock:
            results.append((code, body, parsed, idx))
        status = parsed.get("status") if isinstance(parsed, dict) else None
        print(f"[worker {idx}] HTTP {code}  status={status!r}")
        if parsed is not None:
            print(f"           body: {json.dumps(parsed, ensure_ascii=False)}")
        else:
            print(f"           raw: {body[:500]!r}")

    with ThreadPoolExecutor(max_workers=n) as ex:
        futs = [ex.submit(task, i) for i in range(n)]
        for f in as_completed(futs):
            f.result()

    ok = 0
    duplicate = 0
    ignored = 0
    other_2xx = 0
    errors = 0

    for code, _body, parsed, _idx in sorted(results, key=lambda x: x[3]):
        if code != 200:
            errors += 1
            continue
        if not isinstance(parsed, dict):
            other_2xx += 1
            continue
        st = parsed.get("status")
        if st == "ok":
            ok += 1
        elif st == "duplicate":
            duplicate += 1
        elif st == "ignored":
            ignored += 1
        else:
            other_2xx += 1

    valid_true = sum(
        1
        for _c, _b, p, _i in results
        if isinstance(p, dict) and p.get("status") == "ok" and p.get("is_valid") is True
    )

    print("-" * 60)
    print("Summary (HTTP 200 bodies):")
    print(f"  status=ok:        {ok}")
    print(f"  status=duplicate: {duplicate}")
    print(f"  status=ignored:   {ignored}")
    print(f"  other 200:        {other_2xx}")
    print(f"  non-200 / errors: {errors}")
    print(f"  ok + is_valid true: {valid_true}")
    print()
    print(
        "Expectation (antifraud): at most one new economically valid listen per "
        "(user, song) in the 2h / daily-cap window; parallel ok responses may "
        "include is_valid=false or duplicate if idempotency keys collide."
    )

    cnt, dberr = _db_recent_count(db_path, args.user_id, args.song_id)
    print("-" * 60)
    print(f"DB ({db_path}):")
    if cnt is not None:
        print(
            f"  ListeningEvent rows (user_id={args.user_id}, song_id={args.song_id}, "
            f"created_at in last 1 minute): {cnt}"
        )
    else:
        print(f"  Could not query: {dberr}")


if __name__ == "__main__":
    main()
