"""Add metadata foundation entities and song fields.

Revision ID: 0002_metadata_foundation
Revises: 0001_bootstrap
Create Date: 2026-04-13
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002_metadata_foundation"
down_revision: Union[str, Sequence[str], None] = "0001_bootstrap"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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


def _fk_exists(bind, table_name: str, fk_name: str) -> bool:
    if not table_exists(bind, table_name):
        return False
    inspector = sa.inspect(bind)
    return any(str(fk.get("name")) == fk_name for fk in inspector.get_foreign_keys(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if not table_exists(bind, "genres"):
        op.create_table(
            "genres",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.UniqueConstraint("name", name="uq_genres_name"),
        )
    if not _index_exists(bind, "genres", "ix_genres_name"):
        op.create_index("ix_genres_name", "genres", ["name"], unique=True)

    if not table_exists(bind, "subgenres"):
        op.create_table(
            "subgenres",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("genre_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.ForeignKeyConstraint(["genre_id"], ["genres.id"]),
            sa.UniqueConstraint("genre_id", "name", name="uq_subgenres_genre_name"),
        )
    if not _index_exists(bind, "subgenres", "ix_subgenres_genre_id"):
        op.create_index("ix_subgenres_genre_id", "subgenres", ["genre_id"], unique=False)

    moods_type = postgresql.ARRAY(sa.String()) if dialect == "postgresql" else sa.JSON()

    if not column_exists(bind, "songs", "genre_id"):
        op.add_column("songs", sa.Column("genre_id", sa.Integer(), nullable=True))
    if not column_exists(bind, "songs", "subgenre_id"):
        op.add_column("songs", sa.Column("subgenre_id", sa.Integer(), nullable=True))
    if not column_exists(bind, "songs", "moods"):
        op.add_column("songs", sa.Column("moods", moods_type, nullable=True))
    if not column_exists(bind, "songs", "country_code"):
        op.add_column("songs", sa.Column("country_code", sa.String(length=2), nullable=True))
    if not column_exists(bind, "songs", "city"):
        op.add_column("songs", sa.Column("city", sa.String(length=128), nullable=True))

    # SQLite cannot add new FK constraints to existing tables via ALTER TABLE.
    if dialect != "sqlite":
        if not _fk_exists(bind, "songs", "fk_songs_genre_id_genres"):
            op.create_foreign_key(
                "fk_songs_genre_id_genres",
                "songs",
                "genres",
                ["genre_id"],
                ["id"],
            )
        if not _fk_exists(bind, "songs", "fk_songs_subgenre_id_subgenres"):
            op.create_foreign_key(
                "fk_songs_subgenre_id_subgenres",
                "songs",
                "subgenres",
                ["subgenre_id"],
                ["id"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect != "sqlite":
        if _fk_exists(bind, "songs", "fk_songs_subgenre_id_subgenres"):
            op.drop_constraint("fk_songs_subgenre_id_subgenres", "songs", type_="foreignkey")
        if _fk_exists(bind, "songs", "fk_songs_genre_id_genres"):
            op.drop_constraint("fk_songs_genre_id_genres", "songs", type_="foreignkey")

    if column_exists(bind, "songs", "city"):
        op.drop_column("songs", "city")
    if column_exists(bind, "songs", "country_code"):
        op.drop_column("songs", "country_code")
    if column_exists(bind, "songs", "moods"):
        op.drop_column("songs", "moods")
    if column_exists(bind, "songs", "subgenre_id"):
        op.drop_column("songs", "subgenre_id")
    if column_exists(bind, "songs", "genre_id"):
        op.drop_column("songs", "genre_id")

    if _index_exists(bind, "subgenres", "ix_subgenres_genre_id"):
        op.drop_index("ix_subgenres_genre_id", table_name="subgenres")
    if table_exists(bind, "subgenres"):
        op.drop_table("subgenres")

    if _index_exists(bind, "genres", "ix_genres_name"):
        op.drop_index("ix_genres_name", table_name="genres")
    if table_exists(bind, "genres"):
        op.drop_table("genres")
