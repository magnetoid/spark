"""reliability: stable idempotency key per post target, channel health checks and alerts

Revision ID: 7182930415a6
Revises: 607182930415
"""

import sqlalchemy as sa

from alembic import op

revision = "7182930415a6"
down_revision = "607182930415"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("post_targets") as batch:
        batch.add_column(
            sa.Column("publish_epoch", sa.Integer(), nullable=False, server_default="0")
        )
    with op.batch_alter_table("social_accounts") as batch:
        batch.add_column(sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("alerted_for", sa.String(24), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("social_accounts") as batch:
        batch.drop_column("alerted_for")
        batch.drop_column("checked_at")
    with op.batch_alter_table("post_targets") as batch:
        batch.drop_column("publish_epoch")
