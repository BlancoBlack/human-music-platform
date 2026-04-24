"""Add onboarding step/sub-role and onboarding preferences/profile fields.

Revision ID: 0017_onboarding_profile_and_user_state
Revises: 0016_registration_roles_onboarding_labels
Create Date: 2026-04-24
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0017_onboarding_profile_and_user_state"
down_revision: Union[str, Sequence[str], None] = "0016_registration_roles_onboarding_labels"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(bind, table_name: str) -> set[str]:
    insp = sa.inspect(bind)
    return {c["name"] for c in insp.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()

    user_cols = _column_names(bind, "users")
    if "onboarding_step" not in user_cols:
        op.add_column("users", sa.Column("onboarding_step", sa.String(length=64), nullable=True))
    if "sub_role" not in user_cols:
        op.add_column("users", sa.Column("sub_role", sa.String(length=32), nullable=True))

    profile_cols = _column_names(bind, "user_profiles")
    if "bio" not in profile_cols:
        op.add_column("user_profiles", sa.Column("bio", sa.String(length=1024), nullable=True))
    if "preferred_genres" not in profile_cols:
        op.add_column("user_profiles", sa.Column("preferred_genres", sa.JSON(), nullable=True))
    if "preferred_artists" not in profile_cols:
        op.add_column("user_profiles", sa.Column("preferred_artists", sa.JSON(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    user_cols = _column_names(bind, "users")
    profile_cols = _column_names(bind, "user_profiles")

    if "preferred_artists" in profile_cols:
        op.drop_column("user_profiles", "preferred_artists")
    if "preferred_genres" in profile_cols:
        op.drop_column("user_profiles", "preferred_genres")
    if "bio" in profile_cols:
        op.drop_column("user_profiles", "bio")
    if "sub_role" in user_cols:
        op.drop_column("users", "sub_role")
    if "onboarding_step" in user_cols:
        op.drop_column("users", "onboarding_step")
