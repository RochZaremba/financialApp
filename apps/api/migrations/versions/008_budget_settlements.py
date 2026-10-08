"""Immutable monthly settlements and remembered surplus ratios."""

from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"


def columns():
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("household_id", sa.String(36), sa.ForeignKey("households.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(36)),
        sa.Column("updated_by", sa.String(36)),
    ]


def upgrade():
    op.create_table(
        "budget_settlements",
        *columns(),
        sa.Column("source_month", sa.String(7), nullable=False),
        sa.Column("target_month", sa.String(7), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.UniqueConstraint("household_id", "source_month"),
    )
    op.create_index("ix_budget_settlements_household_id", "budget_settlements", ["household_id"])
    op.create_table(
        "surplus_policies",
        *columns(),
        sa.Column("targets", sa.JSON(), nullable=False),
        sa.Column("account_id", sa.String(36), sa.ForeignKey("accounts.id"), nullable=False),
        sa.UniqueConstraint("household_id"),
    )
    op.create_index("ix_surplus_policies_household_id", "surplus_policies", ["household_id"])


def downgrade():
    op.execute(
        """DO $$ BEGIN IF EXISTS(SELECT 1 FROM budget_settlements) OR EXISTS(SELECT 1 FROM surplus_policies) THEN RAISE EXCEPTION 'Cannot discard budget settlements or saved surplus ratios'; END IF; END $$"""
    )
    op.drop_table("surplus_policies")
    op.drop_table("budget_settlements")
