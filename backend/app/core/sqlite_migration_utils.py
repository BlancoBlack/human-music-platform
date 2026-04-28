"""SQLite migration safety helpers for Alembic batch operations."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import sqlalchemy as sa
from sqlalchemy import text

logger = logging.getLogger(__name__)


def is_sqlite(bind) -> bool:
    return bind.dialect.name == "sqlite"


def get_foreign_keys_pragma(bind) -> int:
    return int(bind.execute(text("PRAGMA foreign_keys")).scalar() or 0)


def disable_foreign_keys(bind) -> None:
    logger.warning("sqlite_fk_disable_requested")
    bind.execute(text("PRAGMA foreign_keys=OFF"))


def enable_foreign_keys(bind) -> None:
    bind.execute(text("PRAGMA foreign_keys=ON"))


def restore_foreign_keys(bind, prior_state: int | bool | None) -> None:
    bind.execute(text(f"PRAGMA foreign_keys={1 if prior_state else 0}"))


def foreign_key_violations(bind) -> list[tuple[Any, ...]]:
    rows = bind.execute(text("PRAGMA foreign_key_check")).fetchall()
    return [tuple(r) for r in rows]


def list_alembic_tmp_tables(bind) -> list[str]:
    rows = bind.execute(
        text(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name LIKE '_alembic_tmp_%'"
        )
    ).fetchall()
    return [str(r[0]) for r in rows if r and r[0]]


def cleanup_alembic_tmp_tables(bind) -> list[str]:
    names = list_alembic_tmp_tables(bind)
    for name in names:
        bind.execute(text(f'DROP TABLE IF EXISTS "{name}"'))
    if names:
        logger.warning("sqlite_alembic_tmp_tables_cleaned", extra={"tables": names})
    return names


def migration_preflight_issues(bind) -> list[str]:
    issues: list[str] = []
    tmp_tables = list_alembic_tmp_tables(bind)
    if tmp_tables:
        issues.append(f"Found stale Alembic temp tables: {tmp_tables}")

    violations = foreign_key_violations(bind)
    if violations:
        issues.append(f"Foreign key violations detected: {violations}")

    inspector = sa.inspect(bind)
    if "alembic_version" in inspector.get_table_names():
        rows = bind.execute(text("SELECT version_num FROM alembic_version")).fetchall()
        versions = [str(r[0]) for r in rows if r and r[0]]
        if len(versions) != 1:
            issues.append(
                "alembic_version is inconsistent (expected 1 row, "
                f"found {len(versions)}): {versions}"
            )
    return issues


def check_migration_safety(bind) -> None:
    issues = migration_preflight_issues(bind)
    if not issues:
        return
    logger.error("sqlite_migration_preflight_failed", extra={"issues": issues})
    raise RuntimeError(
        "Migration safety preflight failed. "
        + " | ".join(issues)
        + " | Suggested fixes: drop _alembic_tmp_* tables, resolve FK violations "
        "(`PRAGMA foreign_key_check`), and repair alembic_version manually if needed."
    )


def safe_sqlite_batch_op(
    op_module,
    table_name: str,
    fn: Callable[[Any], None],
    *,
    batch_kwargs: dict[str, Any] | None = None,
) -> None:
    bind = op_module.get_bind()
    kwargs = batch_kwargs or {}
    if not is_sqlite(bind):
        with op_module.batch_alter_table(table_name, **kwargs) as batch_op:
            fn(batch_op)
        return

    sqlite_fk_state = get_foreign_keys_pragma(bind)
    disable_foreign_keys(bind)
    cleanup_alembic_tmp_tables(bind)
    try:
        with op_module.batch_alter_table(table_name, **kwargs) as batch_op:
            fn(batch_op)
    finally:
        restore_foreign_keys(bind, sqlite_fk_state)

    violations = foreign_key_violations(bind)
    if violations:
        raise RuntimeError(
            f"SQLite FK integrity failed after batch operation for {table_name}: {violations}"
        )
