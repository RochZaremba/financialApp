"""Non-monthly expectations and reminder configuration; retain legacy monthly rows."""

from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "006"


def upgrade():
    op.add_column("recurring", sa.Column("frequency", sa.String(12), nullable=False, server_default="monthly"))
    op.add_column("recurring", sa.Column("start_date", sa.Date(), nullable=True))
    op.add_column("recurring", sa.Column("reminder_days", sa.Integer(), nullable=False, server_default="3"))
    op.create_check_constraint("recurring_frequency", "recurring", "frequency in ('weekly','monthly','quarterly','yearly')")
    op.create_check_constraint("recurring_reminder_days", "recurring", "reminder_days between 0 and 30")
    op.create_check_constraint("recurring_anchor", "recurring", "frequency = 'monthly' or start_date is not null")


def downgrade():
    op.execute(
        """DO $$ BEGIN IF EXISTS(SELECT 1 FROM recurring WHERE frequency <> 'monthly' OR start_date IS NOT NULL OR reminder_days <> 3) THEN RAISE EXCEPTION 'Cannot discard configured recurring schedules'; END IF; END $$"""
    )
    for name in ["recurring_anchor", "recurring_reminder_days", "recurring_frequency"]:
        op.drop_constraint(name, "recurring", type_="check")
    for name in ["reminder_days", "start_date", "frequency"]:
        op.drop_column("recurring", name)
