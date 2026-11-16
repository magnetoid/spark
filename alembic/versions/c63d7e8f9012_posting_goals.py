"""Posting goals: a weekly target per channel, since when it holds, one alert a week per brand

Revision ID: c63d7e8f9012
Revises: b52c6d7e8f90
Create Date: 2026-11-16
"""

import sqlalchemy as sa

from alembic import op

revision = "c63d7e8f9012"
down_revision = "b52c6d7e8f90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("social_accounts") as b:
        b.add_column(sa.Column("posting_goal", sa.Integer(), nullable=True))
        b.add_column(sa.Column("posting_goal_since", sa.DateTime(timezone=True), nullable=True))
    with op.batch_alter_table("brands") as b:
        b.add_column(sa.Column("goal_alert_week", sa.String(10), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("brands") as b:
        b.drop_column("goal_alert_week")
    with op.batch_alter_table("social_accounts") as b:
        b.drop_column("posting_goal_since")
        b.drop_column("posting_goal")
