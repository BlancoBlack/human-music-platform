"""Add slug columns to genres and subgenres; unique indexes.

Revision ID: 0009_genre_subgenre_slugs
Revises: 0008_release_media_assets
Create Date: 2026-04-13
"""

from __future__ import annotations

import re
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision: str = "0009_genre_subgenre_slugs"
down_revision: Union[str, Sequence[str], None] = "0008_release_media_assets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _slugify(label: str) -> str:
    s = (label or "").strip().lower()
    s = s.replace("&", " and ")
    s = s.replace("/", " ")
    s = _NON_ALNUM.sub("-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "unknown"


def table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def column_exists(bind, table_name: str, column_name: str) -> bool:
    if not table_exists(bind, table_name):
        return False
    inspector = sa.inspect(bind)
    cols = inspector.get_columns(table_name)
    return any(str(c.get("name")) == column_name for c in cols)


def _index_exists(bind, table_name: str, index_name: str) -> bool:
    if not table_exists(bind, table_name):
        return False
    inspector = sa.inspect(bind)
    return any(str(i.get("name")) == index_name for i in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()

    if table_exists(bind, "genres") and not column_exists(bind, "genres", "slug"):
        op.add_column("genres", sa.Column("slug", sa.String(length=128), nullable=True))

    if table_exists(bind, "subgenres") and not column_exists(bind, "subgenres", "slug"):
        op.add_column("subgenres", sa.Column("slug", sa.String(length=128), nullable=True))

    # Backfill genre slugs
    if table_exists(bind, "genres") and column_exists(bind, "genres", "slug"):
        rows = bind.execute(text("SELECT id, name FROM genres")).fetchall()
        used: set[str] = set()
        for row in rows:
            rid, name = int(row[0]), str(row[1] or "")
            base = _slugify(name)
            slug = base
            n = 2
            while slug in used:
                slug = f"{base}-{n}"
                n += 1
            used.add(slug)
            bind.execute(
                text("UPDATE genres SET slug = :slug WHERE id = :id"),
                {"slug": slug, "id": rid},
            )

    # Backfill subgenre slugs (globally unique within table)
    if table_exists(bind, "subgenres") and column_exists(bind, "subgenres", "slug"):
        rows = bind.execute(text("SELECT id, name FROM subgenres")).fetchall()
        used: set[str] = set()
        for row in rows:
            sid, name = int(row[0]), str(row[1] or "")
            base = _slugify(name)
            slug = base
            n = 2
            while slug in used:
                slug = f"{base}-{n}"
                n += 1
            used.add(slug)
            bind.execute(
                text("UPDATE subgenres SET slug = :slug WHERE id = :id"),
                {"slug": slug, "id": sid},
            )

    dialect = bind.dialect.name

    if table_exists(bind, "genres") and column_exists(bind, "genres", "slug"):
        if dialect == "sqlite":
            with op.batch_alter_table("genres") as batch:
                batch.alter_column(
                    "slug",
                    existing_type=sa.String(length=128),
                    nullable=False,
                )
        else:
            op.alter_column(
                "genres",
                "slug",
                existing_type=sa.String(length=128),
                nullable=False,
            )

    if table_exists(bind, "subgenres") and column_exists(bind, "subgenres", "slug"):
        if dialect == "sqlite":
            with op.batch_alter_table("subgenres") as batch:
                batch.alter_column(
                    "slug",
                    existing_type=sa.String(length=128),
                    nullable=False,
                )
        else:
            op.alter_column(
                "subgenres",
                "slug",
                existing_type=sa.String(length=128),
                nullable=False,
            )

    if table_exists(bind, "genres") and not _index_exists(bind, "genres", "uq_genres_slug"):
        op.create_index("uq_genres_slug", "genres", ["slug"], unique=True)

    if table_exists(bind, "subgenres") and not _index_exists(bind, "subgenres", "uq_subgenres_slug"):
        op.create_index("uq_subgenres_slug", "subgenres", ["slug"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()

    if table_exists(bind, "subgenres") and _index_exists(bind, "subgenres", "uq_subgenres_slug"):
        op.drop_index("uq_subgenres_slug", table_name="subgenres")

    if table_exists(bind, "genres") and _index_exists(bind, "genres", "uq_genres_slug"):
        op.drop_index("uq_genres_slug", table_name="genres")

    if table_exists(bind, "subgenres") and column_exists(bind, "subgenres", "slug"):
        op.drop_column("subgenres", "slug")

    if table_exists(bind, "genres") and column_exists(bind, "genres", "slug"):
        op.drop_column("genres", "slug")
