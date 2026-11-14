"""Wide metrics: reach, views and saves on metrics; app_state for the worker

Revision ID: 8293041a5b6c
Revises: 7182930415a6
Create Date: 2026-11-14
"""

import sqlalchemy as sa

from alembic import op

revision = "8293041a5b6c"
down_revision = "7182930415a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("metrics") as b:
        b.add_column(sa.Column("reach", sa.Integer(), nullable=True))
        b.add_column(sa.Column("views", sa.Integer(), nullable=True))
        b.add_column(sa.Column("saves", sa.Integer(), nullable=True))
    op.create_table(
        "app_state",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("app_state")
    with op.batch_alter_table("metrics") as b:
        b.drop_column("saves")
        b.drop_column("views")
        b.drop_column("reach")
