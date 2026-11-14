"""Report schedules: reports made and emailed weekly or monthly

Revision ID: a41b5c6d7e8f
Revises: 93041a5b6c7d
Create Date: 2026-11-14
"""

import sqlalchemy as sa

from alembic import op

revision = "a41b5c6d7e8f"
down_revision = "93041a5b6c7d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_schedules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "brand_id",
            sa.Integer(),
            sa.ForeignKey("brands.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("cadence", sa.String(16), nullable=False),
        sa.Column("hour", sa.Integer(), nullable=False, server_default="8"),
        sa.Column("recipients", sa.JSON(), nullable=False),
        sa.Column("with_summary", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("share_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_period_end", sa.Date(), nullable=True),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(500), nullable=True),
        sa.Column(
            "created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("report_schedules")
