"""Release cover as ReleaseMediaAsset; drop releases.cover_path.

Revision ID: 0008_release_media_assets
Revises: 0007_release_cover_path
Create Date: 2026-04-13
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision: str = "0008_release_media_assets"
down_revision: Union[str, Sequence[str], None] = "0007_release_cover_path"
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


def upgrade() -> None:
    bind = op.get_bind()

    if not table_exists(bind, "release_media_assets"):
        op.create_table(
            "release_media_assets",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("release_id", sa.Integer(), nullable=False),
            sa.Column("asset_type", sa.String(length=32), nullable=False),
            sa.Column("file_path", sa.String(length=512), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["release_id"], ["releases.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("release_id", "asset_type", name="uq_release_media_assets_release_asset"),
            sa.CheckConstraint(
                "asset_type IN ('COVER_ART')",
                name="ck_release_media_assets_asset_type",
            ),
        )
    if not _index_exists(bind, "release_media_assets", "ix_release_media_assets_id"):
        op.create_index("ix_release_media_assets_id", "release_media_assets", ["id"], unique=False)
    if not _index_exists(bind, "release_media_assets", "ix_release_media_assets_release_id"):
        op.create_index(
            "ix_release_media_assets_release_id",
            "release_media_assets",
            ["release_id"],
            unique=False,
        )

    if table_exists(bind, "releases") and column_exists(bind, "releases", "cover_path"):
        bind.execute(
            text(
                """
                INSERT INTO release_media_assets (release_id, asset_type, file_path, created_at)
                SELECT r.id, 'COVER_ART', TRIM(r.cover_path), CURRENT_TIMESTAMP
                FROM releases r
                WHERE r.cover_path IS NOT NULL
                  AND LENGTH(TRIM(r.cover_path)) > 0
                  AND NOT EXISTS (
                    SELECT 1 FROM release_media_assets x
                    WHERE x.release_id = r.id AND x.asset_type = 'COVER_ART'
                  )
                """
            )
        )
        op.drop_column("releases", "cover_path")


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if table_exists(bind, "releases") and not column_exists(bind, "releases", "cover_path"):
        op.add_column("releases", sa.Column("cover_path", sa.String(length=512), nullable=True))

    if table_exists(bind, "release_media_assets") and column_exists(bind, "releases", "cover_path"):
        if dialect == "sqlite":
            rows = bind.execute(
                text(
                    "SELECT release_id, file_path FROM release_media_assets WHERE asset_type = 'COVER_ART'"
                )
            ).fetchall()
            for rid, fp in rows:
                if rid is None or fp is None:
                    continue
                bind.execute(
                    text("UPDATE releases SET cover_path = :fp WHERE id = :rid"),
                    {"fp": str(fp).strip(), "rid": int(rid)},
                )
        else:
            bind.execute(
                text(
                    """
                    UPDATE releases AS r
                    SET cover_path = a.file_path
                    FROM release_media_assets AS a
                    WHERE a.release_id = r.id AND a.asset_type = 'COVER_ART'
                    """
                )
            )

    if table_exists(bind, "release_media_assets"):
        if _index_exists(bind, "release_media_assets", "ix_release_media_assets_release_id"):
            op.drop_index("ix_release_media_assets_release_id", table_name="release_media_assets")
        if _index_exists(bind, "release_media_assets", "ix_release_media_assets_id"):
            op.drop_index("ix_release_media_assets_id", table_name="release_media_assets")
        op.drop_table("release_media_assets")
