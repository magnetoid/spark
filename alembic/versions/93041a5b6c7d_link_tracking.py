"""Link tracking: clicks tied to a post target, links tied to a post, expiry, longer codes

Revision ID: 93041a5b6c7d
Revises: 8293041a5b6c
Create Date: 2026-11-14
"""

import sqlalchemy as sa

from alembic import op

revision = "93041a5b6c7d"
down_revision = "8293041a5b6c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("short_links") as b:
        b.alter_column("code", existing_type=sa.String(16), type_=sa.String(64))
        b.add_column(sa.Column("post_id", sa.Integer(), nullable=True))
        b.add_column(sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
        b.create_foreign_key(
            "fk_short_links_post_id", "posts", ["post_id"], ["id"], ondelete="SET NULL"
        )
        b.create_index("ix_short_links_post_id", ["post_id"])
    with op.batch_alter_table("link_clicks") as b:
        b.add_column(sa.Column("target_id", sa.Integer(), nullable=True))
        b.create_foreign_key(
            "fk_link_clicks_target_id", "post_targets", ["target_id"], ["id"], ondelete="SET NULL"
        )
        b.create_index("ix_link_clicks_target_id", ["target_id"])


def downgrade() -> None:
    with op.batch_alter_table("link_clicks") as b:
        b.drop_index("ix_link_clicks_target_id")
        b.drop_constraint("fk_link_clicks_target_id", type_="foreignkey")
        b.drop_column("target_id")
    with op.batch_alter_table("short_links") as b:
        b.drop_index("ix_short_links_post_id")
        b.drop_constraint("fk_short_links_post_id", type_="foreignkey")
        b.drop_column("expires_at")
        b.drop_column("post_id")
        b.alter_column("code", existing_type=sa.String(64), type_=sa.String(16))
