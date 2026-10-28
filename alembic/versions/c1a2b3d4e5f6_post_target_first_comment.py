"""post_target first_comment

Revision ID: c1a2b3d4e5f6
Revises: bf4b980a48cd
Create Date: 2026-10-28
"""

import sqlalchemy as sa
from alembic import op

revision = "c1a2b3d4e5f6"
down_revision = "bf4b980a48cd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("post_targets") as batch:
        batch.add_column(sa.Column("first_comment", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("post_targets") as batch:
        batch.drop_column("first_comment")
