"""Add discovery_events telemetry table.

Revision ID: 0032_discovery_events_table
Revises: 0031_release_split_version_source_of_truth
Create Date: 2026-04-29
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0032_discovery_events_table"
down_revision: Union[str, Sequence[str], None] = "0031_release_split_version_source_of_truth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "discovery_events" not in table_names:
        op.create_table(
            "discovery_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("event_type", sa.String(length=64), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("request_id", sa.String(length=64), nullable=False),
            sa.Column("song_id", sa.Integer(), nullable=True),
            sa.Column("artist_id", sa.Integer(), nullable=True),
            sa.Column("section", sa.String(length=32), nullable=True),
            sa.Column("position", sa.Integer(), nullable=True),
            sa.Column("metadata_json", sa.JSON(), nullable=False),
        )

    existing_indexes = {idx["name"] for idx in sa.inspect(bind).get_indexes("discovery_events")}
    index_specs = (
        ("ix_discovery_events_created_at", ["created_at"]),
        ("ix_discovery_events_event_type_created_at", ["event_type", "created_at"]),
        ("ix_discovery_events_request_id", ["request_id"]),
        ("ix_discovery_events_song_id_created_at", ["song_id", "created_at"]),
        ("ix_discovery_events_user_id_created_at", ["user_id", "created_at"]),
    )
    for index_name, columns in index_specs:
        if index_name in existing_indexes:
            continue
        op.create_index(index_name, "discovery_events", columns, unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())
    if "discovery_events" not in table_names:
        return

    existing_indexes = {idx["name"] for idx in inspector.get_indexes("discovery_events")}
    for index_name in (
        "ix_discovery_events_user_id_created_at",
        "ix_discovery_events_song_id_created_at",
        "ix_discovery_events_request_id",
        "ix_discovery_events_event_type_created_at",
        "ix_discovery_events_created_at",
    ):
        if index_name in existing_indexes:
            op.drop_index(index_name, table_name="discovery_events")
    op.drop_table("discovery_events")
