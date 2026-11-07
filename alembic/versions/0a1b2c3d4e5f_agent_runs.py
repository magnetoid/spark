"""agent runs; posts remember the run that proposed them and the time it proposed

Revision ID: 0a1b2c3d4e5f
Revises: f0a1b2c3d4e5
Create Date: 2026-11-07
"""

import sqlalchemy as sa
from alembic import op

revision = "0a1b2c3d4e5f"
down_revision = "f0a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("brand_id", sa.Integer(), sa.ForeignKey("brands.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("kind", sa.String(length=24), nullable=False, server_default="ask"),
        sa.Column("prompt", sa.Text(), nullable=False, server_default=""),
        sa.Column("janus_run_id", sa.String(length=64), nullable=True),
        sa.Column("session_key", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="queued"),
        sa.Column("output", sa.Text(), nullable=True),
        sa.Column("proposal", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("events", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("usage", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_agent_runs_brand_id", "agent_runs", ["brand_id"])
    op.create_index("ix_agent_runs_janus_run_id", "agent_runs", ["janus_run_id"])
    op.create_index("ix_agent_runs_status", "agent_runs", ["status"])
    with op.batch_alter_table("posts") as b:
        b.add_column(sa.Column("agent_run_id", sa.Integer(), sa.ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True))
        b.add_column(sa.Column("proposed_for", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("posts") as b:
        b.drop_column("proposed_for")
        b.drop_column("agent_run_id")
    op.drop_table("agent_runs")
