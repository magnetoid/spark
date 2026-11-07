"""media dimensions, tags and source; post format per target

Revision ID: 1b2c3d4e5f60
Revises: 0a1b2c3d4e5f
Create Date: 2026-11-07
"""

import sqlalchemy as sa
from alembic import op

revision = "1b2c3d4e5f60"
down_revision = "0a1b2c3d4e5f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("media") as b:
        b.add_column(sa.Column("width", sa.Integer(), nullable=True))
        b.add_column(sa.Column("height", sa.Integer(), nullable=True))
        b.add_column(sa.Column("duration_s", sa.Float(), nullable=True))
        b.add_column(sa.Column("tags", sa.JSON(), nullable=False, server_default="[]"))
        b.add_column(sa.Column("source", sa.String(length=16), nullable=False, server_default="upload"))
    with op.batch_alter_table("post_targets") as b:
        b.add_column(sa.Column("post_type", sa.String(length=16), nullable=False, server_default="post"))


def downgrade() -> None:
    with op.batch_alter_table("post_targets") as b:
        b.drop_column("post_type")
    with op.batch_alter_table("media") as b:
        b.drop_column("source")
        b.drop_column("tags")
        b.drop_column("duration_s")
        b.drop_column("height")
        b.drop_column("width")
