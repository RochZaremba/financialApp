"""Named monthly income sources; keep legacy totals for image rollback."""

from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"


def upgrade():
    op.create_table(
        "income_sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("household_id", sa.String(36), sa.ForeignKey("households.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period_id", sa.String(36), sa.ForeignKey("periods.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("member_id", sa.String(36), sa.ForeignKey("members.id"), nullable=True),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(36), nullable=True),
        sa.Column("updated_by", sa.String(36), nullable=True),
        sa.UniqueConstraint("period_id", "position"),
        sa.CheckConstraint("amount between 0 and 100000000000"),
        sa.CheckConstraint("position >= 0"),
    )
    op.create_index("ix_income_sources_household_id", "income_sources", ["household_id"])
    op.create_index("ix_income_sources_period_id", "income_sources", ["period_id"])
    op.execute("""INSERT INTO income_sources
        (id, household_id, period_id, name, member_id, amount, position, created_at, updated_at, created_by, updated_by)
        SELECT id, household_id, id, 'Dochód wspólny', NULL, planned_income, 0,
            created_at, updated_at, created_by, updated_by
        FROM periods WHERE planned_income > 0""")


def downgrade():
    # Prevent losing names/contributors through an automatic schema downgrade.
    # Older application images can keep using periods.planned_income unchanged.
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM income_sources) THEN
            RAISE EXCEPTION 'Cannot downgrade while named income sources exist; roll back application images instead';
        END IF;
    END $$""")
    op.drop_table("income_sources")
