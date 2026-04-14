"""Add release container model and song.release_id.

Revision ID: 0004_release_container
Revises: 0003_song_state_machine
Create Date: 2026-04-13
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_release_container"
down_revision: Union[str, Sequence[str], None] = "0003_song_state_machine"
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


def _check_exists(bind, table_name: str, check_name: str) -> bool:
    if not table_exists(bind, table_name):
        return False
    inspector = sa.inspect(bind)
    return any(str(c.get("name")) == check_name for c in inspector.get_check_constraints(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if not table_exists(bind, "releases"):
        op.create_table(
            "releases",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("artist_id", sa.Integer(), nullable=False),
            sa.Column("type", sa.String(length=32), nullable=False),
            sa.Column("release_date", sa.DateTime(), nullable=False),
            sa.Column("discoverable_at", sa.DateTime(), nullable=True),
            sa.Column("state", sa.String(length=32), nullable=False, server_default="draft"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["artist_id"], ["artists.id"]),
        )

    if not _index_exists(bind, "releases", "ix_releases_id"):
        op.create_index("ix_releases_id", "releases", ["id"], unique=False)
    if not _index_exists(bind, "releases", "ix_releases_artist_id"):
        op.create_index("ix_releases_artist_id", "releases", ["artist_id"], unique=False)

    if dialect != "sqlite":
        if not _check_exists(bind, "releases", "ck_releases_type_values"):
            op.create_check_constraint(
                "ck_releases_type_values",
                "releases",
                "type IN ('single', 'album')",
            )
        if not _check_exists(bind, "releases", "ck_releases_state_values"):
            op.create_check_constraint(
                "ck_releases_state_values",
                "releases",
                "state IN ('draft', 'scheduled', 'published', 'frozen')",
            )

    if not column_exists(bind, "songs", "release_id"):
        op.add_column("songs", sa.Column("release_id", sa.Integer(), nullable=True))

    # SQLite cannot add FK constraints to existing tables via ALTER TABLE.
    if dialect != "sqlite" and not _fk_exists(bind, "songs", "fk_songs_release_id_releases"):
        op.create_foreign_key(
            "fk_songs_release_id_releases",
            "songs",
            "releases",
            ["release_id"],
            ["id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect != "sqlite" and _fk_exists(bind, "songs", "fk_songs_release_id_releases"):
        op.drop_constraint("fk_songs_release_id_releases", "songs", type_="foreignkey")

    if column_exists(bind, "songs", "release_id"):
        op.drop_column("songs", "release_id")

    if dialect != "sqlite":
        if _check_exists(bind, "releases", "ck_releases_state_values"):
            op.drop_constraint("ck_releases_state_values", "releases", type_="check")
        if _check_exists(bind, "releases", "ck_releases_type_values"):
            op.drop_constraint("ck_releases_type_values", "releases", type_="check")
    if _index_exists(bind, "releases", "ix_releases_artist_id"):
        op.drop_index("ix_releases_artist_id", table_name="releases")
    if _index_exists(bind, "releases", "ix_releases_id"):
        op.drop_index("ix_releases_id", table_name="releases")
    if table_exists(bind, "releases"):
        op.drop_table("releases")
