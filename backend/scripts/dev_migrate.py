from __future__ import annotations

import sys
from pathlib import Path

from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _BACKEND_ROOT.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.core.database import engine
from app.core.sqlite_migration_utils import check_migration_safety, is_sqlite


def _alembic_config() -> AlembicConfig:
    return AlembicConfig(str(_BACKEND_ROOT / "alembic.ini"))


def main() -> int:
    print("== Dev migration ==")
    try:
        with engine.connect() as conn:
            if is_sqlite(conn):
                print("1) Running SQLite migration preflight...")
                check_migration_safety(conn)

        print("2) Running alembic upgrade head...")
        cfg = _alembic_config()
        cfg.attributes["skip_logging_config"] = True
        alembic_command.upgrade(cfg, "head")
    except Exception as exc:
        print(f"FAIL: {exc}")
        return 1

    print("SUCCESS: Database is at Alembic head.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
