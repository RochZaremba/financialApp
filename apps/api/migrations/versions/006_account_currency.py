"""Native account balance currency; existing accounts remain PLN."""

from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "005"


def upgrade():
    op.add_column("accounts", sa.Column("currency", sa.String(3), nullable=False, server_default="PLN"))
    op.create_check_constraint("accounts_currency", "accounts", "currency in ('PLN','EUR','USD','GBP','CHF')")


def downgrade():
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM accounts WHERE currency <> 'PLN') THEN
            RAISE EXCEPTION 'Cannot discard foreign account currencies';
        END IF;
    END $$""")
    op.drop_constraint("accounts_currency", "accounts", type_="check")
    op.drop_column("accounts", "currency")
