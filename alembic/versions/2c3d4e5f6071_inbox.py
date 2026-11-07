"""the smart inbox: items, saved replies, rules

Revision ID: 2c3d4e5f6071
Revises: 1b2c3d4e5f60
Create Date: 2026-11-07
"""

import sqlalchemy as sa
from alembic import op

revision = "2c3d4e5f6071"
down_revision = "1b2c3d4e5f60"
branch_labels = None
depends_on = None


def _ts():
    return (sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))


def upgrade() -> None:
    op.create_table(
        "saved_replies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("brand_id", sa.Integer(), sa.ForeignKey("brands.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("shortcut", sa.String(length=40), nullable=True),
        sa.Column("uses", sa.Integer(), nullable=False, server_default="0"),
        *_ts(),
    )
    op.create_index("ix_saved_replies_brand_id", "saved_replies", ["brand_id"])
    op.create_table(
        "inbox_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("brand_id", sa.Integer(), sa.ForeignKey("brands.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("kinds", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("platforms", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("keywords", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("intents", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("sentiments", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("saved_reply_id", sa.Integer(), sa.ForeignKey("saved_replies.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reply_text", sa.Text(), nullable=True),
        sa.Column("assign_to_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("hits", sa.Integer(), nullable=False, server_default="0"),
        *_ts(),
    )
    op.create_index("ix_inbox_rules_brand_id", "inbox_rules", ["brand_id"])
    op.create_table(
        "inbox_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("brand_id", sa.Integer(), sa.ForeignKey("brands.id", ondelete="CASCADE"), nullable=False),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("social_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("thread_id", sa.String(length=255), nullable=True),
        sa.Column("parent_external_id", sa.String(length=255), nullable=True),
        sa.Column("direction", sa.String(length=8), nullable=False, server_default="incoming"),
        sa.Column("author_external_id", sa.String(length=255), nullable=True),
        sa.Column("author_name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("author_handle", sa.String(length=200), nullable=True),
        sa.Column("author_picture", sa.String(length=1000), nullable=True),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("permalink", sa.String(length=1000), nullable=True),
        sa.Column("post", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("attachments", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("raw", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column("assignee_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("sentiment", sa.String(length=16), nullable=True),
        sa.Column("intent", sa.String(length=24), nullable=True),
        sa.Column("classified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("suggestions", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("suggested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("draft_reply", sa.Text(), nullable=True),
        sa.Column("draft_rule_id", sa.Integer(), sa.ForeignKey("inbox_rules.id", ondelete="SET NULL"), nullable=True),
        sa.Column("replied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reply_text", sa.Text(), nullable=True),
        sa.Column("replied_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        *_ts(),
        sa.UniqueConstraint("account_id", "kind", "external_id", name="uq_inbox_item"),
    )
    for col in ("brand_id", "account_id", "kind", "thread_id", "received_at", "status"):
        op.create_index(f"ix_inbox_items_{col}", "inbox_items", [col])


def downgrade() -> None:
    op.drop_table("inbox_items")
    op.drop_table("inbox_rules")
    op.drop_table("saved_replies")
