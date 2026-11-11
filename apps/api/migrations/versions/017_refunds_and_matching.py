"""Linked refunds and explicit bank match provenance; additive cash representation."""

from alembic import op
import sqlalchemy as sa

revision = "017"
down_revision = "016"

BALANCE_FUNCTION = """
CREATE OR REPLACE FUNCTION check_transaction_balance() RETURNS trigger AS $$
DECLARE tid varchar; tx transactions%ROWTYPE; original transactions%ROWTYPE; total bigint; origin_id varchar;
BEGIN
  IF TG_TABLE_NAME = 'transactions' THEN
    IF TG_OP = 'DELETE' THEN tid := OLD.id; ELSE tid := NEW.id; END IF;
  ELSE
    IF TG_OP = 'DELETE' THEN tid := OLD.transaction_id; ELSE tid := NEW.transaction_id; END IF;
  END IF;
  SELECT * INTO tx FROM transactions WHERE id = tid;
  IF NOT FOUND THEN RETURN NULL; END IF;
  IF tx.kind = 'expense' AND tx.status = 'categorized' OR tx.refund_of_id IS NOT NULL AND tx.status = 'categorized' THEN
    SELECT coalesce(sum(amount),0) INTO total FROM transaction_allocations WHERE transaction_id = tid;
    IF total != tx.amount THEN RAISE EXCEPTION 'Allocation total does not equal transaction amount' USING ERRCODE = '23514'; END IF;
  END IF;
  IF tx.refund_of_id IS NULL AND NOT EXISTS(SELECT 1 FROM transactions WHERE refund_of_id=tx.id) THEN RETURN NULL; END IF;
  origin_id := coalesce(tx.refund_of_id, CASE WHEN tx.kind = 'expense' THEN tx.id ELSE NULL END);
  IF origin_id IS NULL THEN RETURN NULL; END IF;
  SELECT * INTO original FROM transactions WHERE id = origin_id FOR UPDATE;
  IF NOT FOUND OR original.kind != 'expense' THEN
    RAISE EXCEPTION 'Refund must reference an expense' USING ERRCODE = '23514';
  END IF;
  IF EXISTS(SELECT 1 FROM transactions r WHERE r.refund_of_id = origin_id AND
    (r.household_id != original.household_id OR r.date < original.date OR r.kind != 'income')) THEN
    RAISE EXCEPTION 'Invalid refund household or date' USING ERRCODE = '23514';
  END IF;
  SELECT coalesce(sum(amount),0) INTO total FROM transactions WHERE refund_of_id = origin_id;
  IF total > original.amount THEN RAISE EXCEPTION 'Refund exceeds original expense' USING ERRCODE = '23514'; END IF;
  IF EXISTS(SELECT a.category_id FROM transaction_allocations a JOIN transactions r ON r.id = a.transaction_id
    WHERE r.refund_of_id = origin_id GROUP BY a.category_id HAVING sum(a.amount) >
      coalesce((SELECT sum(o.amount) FROM transaction_allocations o WHERE o.transaction_id = origin_id AND o.category_id = a.category_id),0)) THEN
    RAISE EXCEPTION 'Refund exceeds original category amount' USING ERRCODE = '23514';
  END IF;
  RETURN NULL;
END; $$ LANGUAGE plpgsql;
"""


def upgrade():
    op.add_column("transactions", sa.Column("bank_match_excluded", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("transactions", sa.Column("refund_of_id", sa.String(36), nullable=True))
    op.create_foreign_key(
        "fk_transaction_refund", "transactions", "transactions", ["refund_of_id"], ["id"], deferrable=True, initially="DEFERRED"
    )
    op.create_index("ix_transactions_refund_of_id", "transactions", ["refund_of_id"])
    op.create_check_constraint(
        "transaction_refund_shape",
        "transactions",
        "refund_of_id is null or (kind = 'income' and destination_id is null and refund_of_id != id)",
    )
    op.add_column("bank_entries", sa.Column("match_method", sa.String(16), nullable=True))
    op.add_column("bank_entries", sa.Column("auto_refund_eligible", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("ix_bank_entries_transaction_id", "bank_entries", ["transaction_id"])
    op.execute(BALANCE_FUNCTION)


def downgrade():
    op.execute(
        "DO $$ BEGIN IF EXISTS(SELECT 1 FROM transactions WHERE refund_of_id IS NOT NULL) OR EXISTS(SELECT 1 FROM bank_entries WHERE match_method IS NOT NULL) OR EXISTS(SELECT 1 FROM transactions WHERE bank_match_excluded) THEN RAISE EXCEPTION 'Cannot discard refund or matching history'; END IF; END $$"
    )
    op.execute("""CREATE OR REPLACE FUNCTION check_transaction_balance() RETURNS trigger AS $$
    DECLARE tid varchar; tx_kind varchar; tx_status varchar; tx_amount bigint; total bigint;
    BEGIN
      IF TG_TABLE_NAME = 'transactions' THEN
        IF TG_OP = 'DELETE' THEN tid := OLD.id; ELSE tid := NEW.id; END IF;
      ELSE
        IF TG_OP = 'DELETE' THEN tid := OLD.transaction_id; ELSE tid := NEW.transaction_id; END IF;
      END IF;
      SELECT kind,status,amount INTO tx_kind,tx_status,tx_amount FROM transactions WHERE id=tid;
      IF tx_kind='expense' AND tx_status='categorized' THEN
        SELECT coalesce(sum(amount),0) INTO total FROM transaction_allocations WHERE transaction_id=tid;
        IF total != tx_amount THEN RAISE EXCEPTION 'Allocation total does not equal transaction amount' USING ERRCODE='23514'; END IF;
      END IF;
      RETURN NULL;
    END; $$ LANGUAGE plpgsql;""")
    op.drop_index("ix_bank_entries_transaction_id", table_name="bank_entries")
    op.drop_column("bank_entries", "match_method")
    op.drop_column("bank_entries", "auto_refund_eligible")
    op.drop_constraint("transaction_refund_shape", "transactions", type_="check")
    op.drop_index("ix_transactions_refund_of_id", table_name="transactions")
    op.drop_constraint("fk_transaction_refund", "transactions", type_="foreignkey")
    op.drop_column("transactions", "refund_of_id")
    op.drop_column("transactions", "bank_match_excluded")
