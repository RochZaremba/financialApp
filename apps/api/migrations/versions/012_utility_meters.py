"""Optional meters and confirmed cumulative readings, separate from finances."""

from alembic import op
import sqlalchemy as sa

revision = "012"
down_revision = "011"


def record():
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
        "meters",
        *record(),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("unit", sa.String(8), nullable=False),
        sa.Column("interval_days", sa.Integer, nullable=False),
        sa.CheckConstraint("unit in ('kWh','m3','GJ')"),
        sa.CheckConstraint("interval_days between 0 and 365"),
    )
    op.create_table(
        "meter_photos",
        *record(),
        sa.Column("meter_id", sa.String(36), sa.ForeignKey("meters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("path", sa.String(200), nullable=False),
        sa.Column("image_hash", sa.String(64), nullable=False),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("proposal", sa.JSON(), nullable=True),
        sa.Column("diagnostics", sa.JSON(), nullable=False),
        sa.UniqueConstraint("meter_id", "key"),
    )
    op.create_table(
        "meter_readings",
        *record(),
        sa.Column("meter_id", sa.String(36), sa.ForeignKey("meters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("value", sa.BigInteger, nullable=False),
        sa.Column("photo_id", sa.String(36), sa.ForeignKey("meter_photos.id", ondelete="SET NULL")),
        sa.UniqueConstraint("meter_id", "date"),
        sa.CheckConstraint("value between 0 and 1000000000000"),
    )
    for table in ("meter_photos", "meter_readings"):
        op.create_index(f"ix_{table}_meter_id", table, ["meter_id"])


def downgrade():
    op.execute(
        "DO $$ BEGIN IF EXISTS(SELECT 1 FROM meters) OR EXISTS(SELECT 1 FROM meter_photos) OR EXISTS(SELECT 1 FROM meter_readings) THEN RAISE EXCEPTION 'Cannot discard utility meter history'; END IF; END $$"
    )
    op.drop_table("meter_readings")
    op.drop_table("meter_photos")
    op.drop_table("meters")
