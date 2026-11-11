"""Monthly buffer configuration and auditable account-only balance corrections."""

from alembic import op
import sqlalchemy as sa

revision = "018"
down_revision = "017"


def upgrade():
    op.add_column("periods", sa.Column("buffer_category_id", sa.String(36), nullable=True))
    op.create_foreign_key("fk_period_buffer", "periods", "categories", ["buffer_category_id"], ["id"])
    op.execute("""UPDATE periods p SET buffer_category_id = a.reference_id FROM budget_allocations a
      WHERE a.period_id=p.id AND a.kind='category' AND lower(trim(a.label))='bufor'
      AND NOT EXISTS(SELECT 1 FROM budget_settlements s WHERE s.household_id=p.household_id AND s.source_month=p.month)
      AND (SELECT count(*) FROM budget_allocations b WHERE b.period_id=p.id AND b.kind='category' AND lower(trim(b.label))='bufor')=1""")
    op.create_table(
        "account_adjustments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("household_id", sa.String(36), sa.ForeignKey("households.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(36)),
        sa.Column("updated_by", sa.String(36)),
        sa.Column("account_id", sa.String(36), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("balance_before", sa.BigInteger(), nullable=False),
        sa.Column("balance_after", sa.BigInteger(), nullable=False),
        sa.Column("bank_balance_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount != 0 and balance_after - balance_before = amount"),
    )
    op.create_index("ix_account_adjustments_household_id", "account_adjustments", ["household_id"])
    op.create_index("ix_account_adjustments_account_id", "account_adjustments", ["account_id"])


def downgrade():
    op.execute(
        "DO $$ BEGIN IF EXISTS(SELECT 1 FROM account_adjustments) OR EXISTS(SELECT 1 FROM periods WHERE buffer_category_id IS NOT NULL) THEN RAISE EXCEPTION 'Cannot discard buffer or balance adjustment history'; END IF; END $$"
    )
    op.drop_table("account_adjustments")
    op.drop_constraint("fk_period_buffer", "periods", type_="foreignkey")
    op.drop_column("periods", "buffer_category_id")
