"""Add public slugs and slug history for artists/releases/songs.

Revision ID: 0018_public_entity_slugs
Revises: 0017_onboarding_profile_and_user_state
Create Date: 2026-04-25
"""

from __future__ import annotations

import re
import unicodedata
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0018_public_entity_slugs"
down_revision: Union[str, Sequence[str], None] = "0017_onboarding_profile_and_user_state"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NON_ALNUM_RE = re.compile(r"[^a-z0-9\s-]")
_SPACE_HYPHEN_RE = re.compile(r"[\s_-]+")


def _slugify(raw: str | None) -> str:
    text = (raw or "").strip().lower()
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    cleaned = _NON_ALNUM_RE.sub("", ascii_text)
    compact = _SPACE_HYPHEN_RE.sub("-", cleaned).strip("-")
    return compact or "untitled"


def _column_names(bind, table_name: str) -> set[str]:
    insp = sa.inspect(bind)
    return {c["name"] for c in insp.get_columns(table_name)}


def _index_names(bind, table_name: str) -> set[str]:
    insp = sa.inspect(bind)
    return {i["name"] for i in insp.get_indexes(table_name)}


def _unique_constraint_names(bind, table_name: str) -> set[str]:
    insp = sa.inspect(bind)
    return {c["name"] for c in insp.get_unique_constraints(table_name) if c.get("name")}


def _table_names(bind) -> set[str]:
    insp = sa.inspect(bind)
    return set(insp.get_table_names())


def _allocate_unique(base: str, used: set[str]) -> str:
    slug = base
    n = 2
    while slug in used:
        slug = f"{base}-{n}"
        n += 1
    used.add(slug)
    return slug


def _backfill_table_slugs(bind, *, table_name: str, id_col: str, label_col: str) -> dict[int, str]:
    rows = bind.execute(
        sa.text(f"SELECT {id_col} AS id, {label_col} AS label, slug FROM {table_name} ORDER BY {id_col} ASC")
    ).mappings().all()
    used: set[str] = set()
    assigned: dict[int, str] = {}
    for row in rows:
        rid = int(row["id"])
        existing = (row.get("slug") or "").strip().lower()
        label = str(row.get("label") or "")
        base = _slugify(existing or label)
        unique = _allocate_unique(base, used)
        assigned[rid] = unique
        bind.execute(
            sa.text(f"UPDATE {table_name} SET slug = :slug WHERE {id_col} = :rid"),
            {"slug": unique, "rid": rid},
        )
    return assigned


def _insert_history_rows(
    bind,
    *,
    table_name: str,
    fk_col: str,
    slug_map: dict[int, str],
) -> None:
    for entity_id, slug in slug_map.items():
        bind.execute(
            sa.text(
                f"""
                INSERT INTO {table_name} ({fk_col}, slug, is_current)
                VALUES (:entity_id, :slug, 1)
                """
            ),
            {"entity_id": int(entity_id), "slug": slug},
        )


def _ensure_slug_uniqueness(bind, *, table_name: str, constraint_name: str, fallback_index_name: str) -> None:
    """Enforce unique slug without SQLite table rebuilds.

    - Non-SQLite: create unique constraint.
    - SQLite: create unique index fallback (additive and rebuild-free).
    """
    unique_constraints = _unique_constraint_names(bind, table_name)
    indexes = _index_names(bind, table_name)
    if constraint_name in unique_constraints or fallback_index_name in indexes:
        return
    # Backward-compatibility with prior migration runs that used ix_* names.
    legacy_index_name = f"ix_{table_name}_slug"
    if legacy_index_name in indexes:
        return

    if bind.dialect.name == "sqlite":
        op.create_index(fallback_index_name, table_name, ["slug"], unique=True)
        return
    op.create_unique_constraint(constraint_name, table_name, ["slug"])


def upgrade() -> None:
    bind = op.get_bind()

    artist_cols = _column_names(bind, "artists")
    if "slug" not in artist_cols:
        op.add_column("artists", sa.Column("slug", sa.String(), nullable=True))

    release_cols = _column_names(bind, "releases")
    if "slug" not in release_cols:
        op.add_column("releases", sa.Column("slug", sa.String(), nullable=True))

    song_cols = _column_names(bind, "songs")
    if "slug" not in song_cols:
        op.add_column("songs", sa.Column("slug", sa.String(), nullable=True))

    existing_tables = _table_names(bind)
    if "artist_slug_history" not in existing_tables:
        op.create_table(
            "artist_slug_history",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("artist_id", sa.Integer(), sa.ForeignKey("artists.id", ondelete="CASCADE"), nullable=False),
            sa.Column("slug", sa.String(length=255), nullable=False),
            sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
    if "release_slug_history" not in existing_tables:
        op.create_table(
            "release_slug_history",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("release_id", sa.Integer(), sa.ForeignKey("releases.id", ondelete="CASCADE"), nullable=False),
            sa.Column("slug", sa.String(length=255), nullable=False),
            sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
    if "song_slug_history" not in existing_tables:
        op.create_table(
            "song_slug_history",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("song_id", sa.Integer(), sa.ForeignKey("songs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("slug", sa.String(length=255), nullable=False),
            sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )

    artist_slugs = _backfill_table_slugs(bind, table_name="artists", id_col="id", label_col="name")
    release_slugs = _backfill_table_slugs(bind, table_name="releases", id_col="id", label_col="title")
    song_slugs = _backfill_table_slugs(bind, table_name="songs", id_col="id", label_col="title")

    _insert_history_rows(
        bind,
        table_name="artist_slug_history",
        fk_col="artist_id",
        slug_map=artist_slugs,
    )
    _insert_history_rows(
        bind,
        table_name="release_slug_history",
        fk_col="release_id",
        slug_map=release_slugs,
    )
    _insert_history_rows(
        bind,
        table_name="song_slug_history",
        fk_col="song_id",
        slug_map=song_slugs,
    )

    _ensure_slug_uniqueness(
        bind,
        table_name="artists",
        constraint_name="uq_artists_slug",
        fallback_index_name="uq_artists_slug",
    )
    _ensure_slug_uniqueness(
        bind,
        table_name="releases",
        constraint_name="uq_releases_slug",
        fallback_index_name="uq_releases_slug",
    )
    _ensure_slug_uniqueness(
        bind,
        table_name="songs",
        constraint_name="uq_songs_slug",
        fallback_index_name="uq_songs_slug",
    )

    artist_hist_idx = _index_names(bind, "artist_slug_history")
    if "ix_artist_slug_history_slug" not in artist_hist_idx:
        op.create_index("ix_artist_slug_history_slug", "artist_slug_history", ["slug"], unique=True)
    if "ix_artist_slug_history_artist_id" not in artist_hist_idx:
        op.create_index("ix_artist_slug_history_artist_id", "artist_slug_history", ["artist_id"], unique=False)
    if "ix_artist_slug_history_is_current" not in artist_hist_idx:
        op.create_index("ix_artist_slug_history_is_current", "artist_slug_history", ["is_current"], unique=False)

    release_hist_idx = _index_names(bind, "release_slug_history")
    if "ix_release_slug_history_slug" not in release_hist_idx:
        op.create_index("ix_release_slug_history_slug", "release_slug_history", ["slug"], unique=True)
    if "ix_release_slug_history_release_id" not in release_hist_idx:
        op.create_index("ix_release_slug_history_release_id", "release_slug_history", ["release_id"], unique=False)
    if "ix_release_slug_history_is_current" not in release_hist_idx:
        op.create_index("ix_release_slug_history_is_current", "release_slug_history", ["is_current"], unique=False)

    song_hist_idx = _index_names(bind, "song_slug_history")
    if "ix_song_slug_history_slug" not in song_hist_idx:
        op.create_index("ix_song_slug_history_slug", "song_slug_history", ["slug"], unique=True)
    if "ix_song_slug_history_song_id" not in song_hist_idx:
        op.create_index("ix_song_slug_history_song_id", "song_slug_history", ["song_id"], unique=False)
    if "ix_song_slug_history_is_current" not in song_hist_idx:
        op.create_index("ix_song_slug_history_is_current", "song_slug_history", ["is_current"], unique=False)

    # Keep slug columns nullable in this migration to avoid SQLite table rebuilds.
    # NOT NULL can be enforced in a future dialect-aware migration.


def downgrade() -> None:
    bind = op.get_bind()

    song_hist_idx = _index_names(bind, "song_slug_history") if "song_slug_history" in _table_names(bind) else set()
    if "ix_song_slug_history_is_current" in song_hist_idx:
        op.drop_index("ix_song_slug_history_is_current", table_name="song_slug_history")
    if "ix_song_slug_history_song_id" in song_hist_idx:
        op.drop_index("ix_song_slug_history_song_id", table_name="song_slug_history")
    if "ix_song_slug_history_slug" in song_hist_idx:
        op.drop_index("ix_song_slug_history_slug", table_name="song_slug_history")
    if "song_slug_history" in _table_names(bind):
        op.drop_table("song_slug_history")

    release_hist_idx = _index_names(bind, "release_slug_history") if "release_slug_history" in _table_names(bind) else set()
    if "ix_release_slug_history_is_current" in release_hist_idx:
        op.drop_index("ix_release_slug_history_is_current", table_name="release_slug_history")
    if "ix_release_slug_history_release_id" in release_hist_idx:
        op.drop_index("ix_release_slug_history_release_id", table_name="release_slug_history")
    if "ix_release_slug_history_slug" in release_hist_idx:
        op.drop_index("ix_release_slug_history_slug", table_name="release_slug_history")
    if "release_slug_history" in _table_names(bind):
        op.drop_table("release_slug_history")

    artist_hist_idx = _index_names(bind, "artist_slug_history") if "artist_slug_history" in _table_names(bind) else set()
    if "ix_artist_slug_history_is_current" in artist_hist_idx:
        op.drop_index("ix_artist_slug_history_is_current", table_name="artist_slug_history")
    if "ix_artist_slug_history_artist_id" in artist_hist_idx:
        op.drop_index("ix_artist_slug_history_artist_id", table_name="artist_slug_history")
    if "ix_artist_slug_history_slug" in artist_hist_idx:
        op.drop_index("ix_artist_slug_history_slug", table_name="artist_slug_history")
    if "artist_slug_history" in _table_names(bind):
        op.drop_table("artist_slug_history")

    song_idx = _index_names(bind, "songs")
    song_uq = _unique_constraint_names(bind, "songs")
    if "uq_songs_slug" in song_uq:
        op.drop_constraint("uq_songs_slug", "songs", type_="unique")
    if "uq_songs_slug" in song_idx:
        op.drop_index("uq_songs_slug", table_name="songs")
    if "ix_songs_slug" in song_idx:
        op.drop_index("ix_songs_slug", table_name="songs")
    song_cols = _column_names(bind, "songs")
    if "slug" in song_cols:
        op.drop_column("songs", "slug")

    release_idx = _index_names(bind, "releases")
    release_uq = _unique_constraint_names(bind, "releases")
    if "uq_releases_slug" in release_uq:
        op.drop_constraint("uq_releases_slug", "releases", type_="unique")
    if "uq_releases_slug" in release_idx:
        op.drop_index("uq_releases_slug", table_name="releases")
    if "ix_releases_slug" in release_idx:
        op.drop_index("ix_releases_slug", table_name="releases")
    release_cols = _column_names(bind, "releases")
    if "slug" in release_cols:
        op.drop_column("releases", "slug")

    artist_idx = _index_names(bind, "artists")
    artist_uq = _unique_constraint_names(bind, "artists")
    if "uq_artists_slug" in artist_uq:
        op.drop_constraint("uq_artists_slug", "artists", type_="unique")
    if "uq_artists_slug" in artist_idx:
        op.drop_index("uq_artists_slug", table_name="artists")
    if "ix_artists_slug" in artist_idx:
        op.drop_index("ix_artists_slug", table_name="artists")
    artist_cols = _column_names(bind, "artists")
    if "slug" in artist_cols:
        op.drop_column("artists", "slug")
