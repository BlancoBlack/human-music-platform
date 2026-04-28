from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _db_paths(repo_root: Path) -> tuple[Path, Path, Path]:
    db = repo_root / "backend" / "dev.db"
    return db, db.with_suffix(".db-shm"), db.with_suffix(".db-wal")


def _delete_dev_db(repo_root: Path) -> None:
    db, shm, wal = _db_paths(repo_root)
    for p in (db, shm, wal):
        if p.exists():
            p.unlink()


def _run_alembic_upgrade(repo_root: Path) -> None:
    cmd = [
        sys.executable,
        "-m",
        "alembic",
        "-c",
        str(repo_root / "backend" / "alembic.ini"),
        "upgrade",
        "head",
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(repo_root),
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "Alembic upgrade failed.\n"
            f"STDOUT:\n{proc.stdout}\n"
            f"STDERR:\n{proc.stderr}"
        )


def _run_dev_migrate(repo_root: Path, expect_success: bool) -> str:
    cmd = [
        sys.executable,
        str(repo_root / "backend" / "scripts" / "dev_migrate.py"),
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(repo_root),
        text=True,
        capture_output=True,
        check=False,
    )
    output = f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    if expect_success and proc.returncode != 0:
        raise RuntimeError(f"dev_migrate.py failed unexpectedly.\n{output}")
    if not expect_success and proc.returncode == 0:
        raise RuntimeError(f"dev_migrate.py unexpectedly succeeded.\n{output}")
    return output


def _inject_dirty_state(repo_root: Path) -> None:
    db_path, _shm, _wal = _db_paths(repo_root)
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE IF NOT EXISTS _alembic_tmp_releases (id INTEGER PRIMARY KEY)"
        )
        conn.commit()
    finally:
        conn.close()


def _repair_dirty_state(repo_root: Path) -> None:
    db_path, _shm, _wal = _db_paths(repo_root)
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute("DROP TABLE IF EXISTS _alembic_tmp_releases")
        conn.commit()
    finally:
        conn.close()


def _assert_sqlite_state(repo_root: Path) -> None:
    db_path, _shm, _wal = _db_paths(repo_root)
    if not db_path.exists():
        raise RuntimeError(f"Database was not created at {db_path}")

    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        required = {"users", "artists", "releases", "songs", "release_participants"}
        missing = sorted(required - set(tables))
        if missing:
            raise RuntimeError(f"Missing required tables after migration: {missing}")

        tmp_tables = sorted(t for t in tables if t.startswith("_alembic_tmp_"))
        if tmp_tables:
            raise RuntimeError(f"Temporary Alembic tables still present: {tmp_tables}")

        fk_violations = cur.execute("PRAGMA foreign_key_check").fetchall()
        if fk_violations:
            raise RuntimeError(f"Foreign key violations detected: {fk_violations}")
    finally:
        conn.close()


def main() -> int:
    repo_root = _repo_root()
    print("== Full migration test (SQLite dev.db) ==")
    print(f"Repo root: {repo_root}")
    try:
        print("A1) Removing existing dev database files...")
        _delete_dev_db(repo_root)
        print("A2) Running alembic upgrade head...")
        _run_alembic_upgrade(repo_root)
        print("A3) Validating database schema and FK integrity...")
        _assert_sqlite_state(repo_root)

        print("B1) Injecting dirty state (_alembic_tmp_* table)...")
        _inject_dirty_state(repo_root)
        print("B2) Verifying preflight blocks migration...")
        blocked_output = _run_dev_migrate(repo_root, expect_success=False)
        if "Migration safety preflight failed" not in blocked_output:
            raise RuntimeError(
                "Expected preflight failure message not found in dev_migrate.py output."
            )
        print("B3) Repairing dirty state manually...")
        _repair_dirty_state(repo_root)
        print("B4) Re-running dev_migrate.py after repair...")
        _run_dev_migrate(repo_root, expect_success=True)
        print("B5) Re-validating database schema and FK integrity...")
        _assert_sqlite_state(repo_root)
    except Exception as exc:
        print(f"FAIL: {exc}")
        return 1

    print("SUCCESS: Full migration test completed (clean + dirty path).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
