"""notifications and webhook events

Revision ID: c7d8e9f0a1b2
Revises: b6c7d8e9f0a1
Create Date: 2026-10-28
"""

import sqlalchemy as sa
from alembic import op

revision = "c7d8e9f0a1b2"
down_revision = "b6c7d8e9f0a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("post_targets") as batch:
        batch.add_column(sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True))
    with op.batch_alter_table("posts") as batch:
        batch.add_column(sa.Column("approval_notified_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "webhook_events",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("event", sa.String(length=64), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("webhook_events")
    with op.batch_alter_table("posts") as batch:
        batch.drop_column("approval_notified_at")
    with op.batch_alter_table("post_targets") as batch:
        batch.drop_column("notified_at")
