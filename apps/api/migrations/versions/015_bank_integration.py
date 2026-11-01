"""Private, household-scoped bank connections, immutable statements and push outbox."""

from alembic import op
import sqlalchemy as sa

revision = "015"
down_revision = "014"


def fields():
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("household_id", sa.String(36), sa.ForeignKey("households.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(36)),
        sa.Column("updated_by", sa.String(36)),
    ]


def col(name, kind, nullable=False):
    return sa.Column(name, kind, nullable=nullable)


def upgrade():
    op.create_table(
        "bank_connections",
        *fields(),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        col("state_hash", sa.String(64), True),
        col("state_expires_at", sa.DateTime(timezone=True), True),
        col("session_cipher", sa.String(2048), True),
        col("valid_until", sa.DateTime(timezone=True), True),
        col("status", sa.String(24)),
        col("next_sync", sa.DateTime(timezone=True), True),
        col("last_sync", sa.DateTime(timezone=True), True),
        col("error_code", sa.String(60), True),
    )
    op.create_table(
        "bank_accounts",
        *fields(),
        sa.Column("connection_id", sa.String(36), sa.ForeignKey("bank_connections.id", ondelete="CASCADE"), nullable=False),
        col("uid_cipher", sa.String(2048)),
        col("identity_hash", sa.String(64)),
        col("last4", sa.String(4)),
        col("currency", sa.String(3)),
        col("iban_hash", sa.String(64), True),
        sa.Column("account_id", sa.String(36), sa.ForeignKey("accounts.id"), nullable=True, unique=True),
        col("start_date", sa.Date(), True),
        col("balance", sa.BigInteger(), True),
        col("balance_at", sa.DateTime(timezone=True), True),
        col("last_sync", sa.DateTime(timezone=True), True),
        sa.UniqueConstraint("household_id", "identity_hash"),
    )
    op.create_index("ix_bank_accounts_connection_id", "bank_accounts", ["connection_id"])
    op.create_table(
        "bank_entries",
        *fields(),
        sa.Column("bank_account_id", sa.String(36), sa.ForeignKey("bank_accounts.id", ondelete="CASCADE"), nullable=False),
        col("reference_hash", sa.String(64)),
        col("reliable", sa.Boolean()),
        col("counterparty_hash", sa.String(64), True),
        col("amount", sa.BigInteger()),
        col("date", sa.Date()),
        col("description", sa.String(160)),
        sa.Column("transaction_id", sa.String(36), sa.ForeignKey("transactions.id", ondelete="SET NULL")),
        col("reviewed", sa.Boolean()),
        sa.UniqueConstraint("bank_account_id", "reference_hash"),
        sa.CheckConstraint("amount != 0"),
    )
    op.create_index("ix_bank_entries_bank_account_id", "bank_entries", ["bank_account_id"])
    op.create_table(
        "bank_subscriptions",
        *fields(),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        col("endpoint_hash", sa.String(64)),
        col("payload_cipher", sa.String(8192)),
        sa.UniqueConstraint("user_id", "endpoint_hash"),
    )
    op.create_table(
        "bank_deliveries",
        *fields(),
        sa.Column("subscription_id", sa.String(36), sa.ForeignKey("bank_subscriptions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entry_id", sa.String(36), sa.ForeignKey("bank_entries.id", ondelete="CASCADE"), nullable=False),
        col("attempts", sa.Integer()),
        col("next_attempt", sa.DateTime(timezone=True)),
        col("delivered_at", sa.DateTime(timezone=True), True),
        sa.UniqueConstraint("subscription_id", "entry_id"),
    )
    for table in ("bank_connections", "bank_accounts", "bank_entries", "bank_subscriptions", "bank_deliveries"):
        op.create_index(f"ix_{table}_household_id", table, ["household_id"])


def downgrade():
    op.execute("DO $$ BEGIN IF EXISTS(SELECT 1 FROM bank_entries) THEN RAISE EXCEPTION 'Cannot discard bank history'; END IF; END $$")
    for table in ("bank_deliveries", "bank_subscriptions", "bank_entries", "bank_accounts", "bank_connections"):
        op.drop_table(table)
