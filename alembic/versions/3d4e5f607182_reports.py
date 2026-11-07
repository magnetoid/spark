"""reports and daily follower snapshots

Revision ID: 3d4e5f607182
Revises: 2c3d4e5f6071
Create Date: 2026-11-07
"""

import sqlalchemy as sa
from alembic import op

revision = "3d4e5f607182"
down_revision = "2c3d4e5f6071"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "follower_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("social_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("followers", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="spark"),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("account_id", "day", name="uq_follower_snapshot"),
    )
    op.create_index("ix_follower_snapshots_account_id", "follower_snapshots", ["account_id"])
    op.create_index("ix_follower_snapshots_day", "follower_snapshots", ["day"])
    op.create_table(
        "reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("brand_id", sa.Integer(), sa.ForeignKey("brands.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("start", sa.Date(), nullable=False),
        sa.Column("end", sa.Date(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("summary", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_reports_brand_id", "reports", ["brand_id"])


def downgrade() -> None:
    op.drop_table("reports")
    op.drop_table("follower_snapshots")
