"""Optional measurement time and daily household context; no invented legacy times."""

from alembic import op
import sqlalchemy as sa

revision = "014"
down_revision = "013"


def upgrade():
    op.add_column("meter_readings", sa.Column("time", sa.String(5), nullable=True))
    op.add_column("meter_readings", sa.Column("activities", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("meter_readings", sa.Column("note", sa.String(240), nullable=False, server_default=""))


def downgrade():
    op.execute(
        "DO $$ BEGIN IF EXISTS(SELECT 1 FROM meter_readings WHERE time IS NOT NULL OR activities::text <> '{}' OR note <> '') THEN RAISE EXCEPTION 'Cannot discard reading context'; END IF; END $$"
    )
    op.drop_column("meter_readings", "note")
    op.drop_column("meter_readings", "activities")
    op.drop_column("meter_readings", "time")
