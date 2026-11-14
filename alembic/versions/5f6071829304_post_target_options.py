"""post target options: AI label, paid partnership, collaborators, poll

Revision ID: 5f6071829304
Revises: 4e5f60718293
"""

import sqlalchemy as sa

from alembic import op

revision = "5f6071829304"
down_revision = "4e5f60718293"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("post_targets") as batch:
        batch.add_column(sa.Column("options", sa.JSON(), nullable=False, server_default="{}"))


def downgrade() -> None:
    with op.batch_alter_table("post_targets") as batch:
        batch.drop_column("options")
