"""Follower goals: a target, an optional date, and where the channel stood when it was set

Revision ID: d74e8f901234
Revises: c63d7e8f9012
Create Date: 2026-11-16
"""

import sqlalchemy as sa

from alembic import op

revision = "d74e8f901234"
down_revision = "c63d7e8f9012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("social_accounts") as b:
        b.add_column(sa.Column("follower_goal", sa.Integer(), nullable=True))
        b.add_column(sa.Column("follower_goal_by", sa.Date(), nullable=True))
        b.add_column(sa.Column("follower_goal_start", sa.Integer(), nullable=True))
        b.add_column(sa.Column("follower_goal_since", sa.Date(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("social_accounts") as b:
        b.drop_column("follower_goal_since")
        b.drop_column("follower_goal_start")
        b.drop_column("follower_goal_by")
        b.drop_column("follower_goal")
