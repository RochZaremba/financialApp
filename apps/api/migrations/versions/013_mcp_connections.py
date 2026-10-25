"""Revocable, hashed, household-bound AI connections."""

from alembic import op
import sqlalchemy as sa

revision = "013"
down_revision = "012"


def upgrade():
    op.create_table(
        "mcp_connections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("household_id", sa.String(36), sa.ForeignKey("households.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("access", sa.String(10), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(36)),
        sa.Column("updated_by", sa.String(36)),
        sa.CheckConstraint("access in ('read','write')"),
    )
    op.create_index("ix_mcp_connections_user_id", "mcp_connections", ["user_id"])
    op.create_index("ix_mcp_connections_household_id", "mcp_connections", ["household_id"])


def downgrade():
    op.drop_table("mcp_connections")
