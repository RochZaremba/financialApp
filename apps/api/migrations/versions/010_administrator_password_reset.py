"""Explicit administrator access and password-reset audit trail."""

from alembic import op
import sqlalchemy as sa

revision = "010"
down_revision = "009"


def upgrade():
    op.add_column("users", sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        "password_reset_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(36)),
        sa.Column("updated_by", sa.String(36)),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("target_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
    )


def downgrade():
    op.execute(
        """DO $$ BEGIN IF EXISTS(SELECT 1 FROM users WHERE is_admin) OR EXISTS(SELECT 1 FROM password_reset_events) THEN RAISE EXCEPTION 'Cannot discard administrator access or password reset audit'; END IF; END $$"""
    )
    op.drop_table("password_reset_events")
    op.drop_column("users", "is_admin")
