"""Approval deadlines: a due date and reminder per waiting post, a rule per brand

Revision ID: b52c6d7e8f90
Revises: a41b5c6d7e8f
Create Date: 2026-11-15
"""

import sqlalchemy as sa

from alembic import op

revision = "b52c6d7e8f90"
down_revision = "a41b5c6d7e8f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("brands") as b:
        b.add_column(sa.Column("approval_lead_hours", sa.Integer(), nullable=True))
        b.add_column(
            sa.Column("approval_timeout", sa.String(16), nullable=False, server_default="wait")
        )
    with op.batch_alter_table("posts") as b:
        b.add_column(sa.Column("approval_due_at", sa.DateTime(timezone=True), nullable=True))
        b.add_column(sa.Column("approval_reminded_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("posts") as b:
        b.drop_column("approval_reminded_at")
        b.drop_column("approval_due_at")
    with op.batch_alter_table("brands") as b:
        b.drop_column("approval_timeout")
        b.drop_column("approval_lead_hours")
