"""two-factor sign-in: authenticator secret, recovery codes, wrong-code pause

Revision ID: 607182930415
Revises: 5f6071829304
"""

import sqlalchemy as sa

from alembic import op

revision = "607182930415"
down_revision = "5f6071829304"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("totp_secret", sa.Text(), nullable=True))
        batch.add_column(
            sa.Column("totp_enabled", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(sa.Column("recovery_codes", sa.JSON(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("totp_last_step", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("totp_failed", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("totp_locked_until", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        for name in (
            "totp_locked_until",
            "totp_failed",
            "totp_last_step",
            "recovery_codes",
            "totp_enabled",
            "totp_secret",
        ):
            batch.drop_column(name)
