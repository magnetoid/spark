"""planning: content pillars, per-channel slots, evergreen posts, brand guardrails and voice profile

Revision ID: f0a1b2c3d4e5
Revises: e9f0a1b2c3d4
Create Date: 2026-11-07
"""

import sqlalchemy as sa
from alembic import op

revision = "f0a1b2c3d4e5"
down_revision = "e9f0a1b2c3d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "content_pillars",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("brand_id", sa.Integer(), sa.ForeignKey("brands.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("color", sa.String(length=16), nullable=False, server_default="#6D4AE0"),
        sa.Column("target_share", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_content_pillars_brand_id", "content_pillars", ["brand_id"])
    with op.batch_alter_table("posts") as b:
        b.add_column(sa.Column("pillar_id", sa.Integer(), sa.ForeignKey("content_pillars.id", ondelete="SET NULL"), nullable=True))
        b.add_column(sa.Column("evergreen", sa.Boolean(), nullable=False, server_default=sa.false()))
        b.add_column(sa.Column("recycle_every_days", sa.Integer(), nullable=True))
        b.add_column(sa.Column("recycled_from_id", sa.Integer(), sa.ForeignKey("posts.id", ondelete="SET NULL"), nullable=True))
    with op.batch_alter_table("queue_slots") as b:
        b.add_column(sa.Column("account_id", sa.Integer(), sa.ForeignKey("social_accounts.id", ondelete="CASCADE"), nullable=True))
    with op.batch_alter_table("brands") as b:
        b.add_column(sa.Column("agent_config", sa.JSON(), nullable=False, server_default="{}"))
        b.add_column(sa.Column("voice_profile", sa.JSON(), nullable=False, server_default="{}"))


def downgrade() -> None:
    with op.batch_alter_table("brands") as b:
        b.drop_column("voice_profile")
        b.drop_column("agent_config")
    with op.batch_alter_table("queue_slots") as b:
        b.drop_column("account_id")
    with op.batch_alter_table("posts") as b:
        b.drop_column("recycled_from_id")
        b.drop_column("recycle_every_days")
        b.drop_column("evergreen")
        b.drop_column("pillar_id")
    op.drop_table("content_pillars")
