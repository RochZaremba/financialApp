"""Safe metadata for the latest failed bank synchronization, compatible with old images."""

from alembic import op
import sqlalchemy as sa

revision = "016"
down_revision = "015"


def upgrade():
    op.add_column("bank_connections", sa.Column("sync_diagnostic", sa.JSON(), nullable=True))


def downgrade():
    op.execute(
        "DO $$ BEGIN IF EXISTS(SELECT 1 FROM bank_connections WHERE sync_diagnostic IS NOT NULL) "
        "THEN RAISE EXCEPTION 'Cannot discard bank synchronization diagnostics'; END IF; END $$"
    )
    op.drop_column("bank_connections", "sync_diagnostic")
