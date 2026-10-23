"""Retain one-time grant consumption independently of accounts/releases."""

from alembic import op
import sqlalchemy as sa

revision = "012"
down_revision = "011"


def upgrade():
    op.create_table(
        "recovery_grant_uses",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("target_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.execute(
        "DO $$ BEGIN IF EXISTS(SELECT 1 FROM recovery_grant_uses) THEN RAISE EXCEPTION 'Cannot discard recovery consumption'; END IF; END $$"
    )
    op.drop_table("recovery_grant_uses")
