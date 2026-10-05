"""Preserve unknown draft amounts and negative receipt discounts."""

from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"


def upgrade():
    op.drop_constraint("receipt_items_check", "receipt_items", type_="check")
    op.alter_column("receipt_items", "amount", existing_type=sa.BigInteger(), nullable=True)
    op.create_check_constraint(
        "ck_receipt_item_draft_amount",
        "receipt_items",
        "(amount is null or amount between -100000000000 and 100000000000) and confidence between 0 and 100",
    )


def downgrade():
    # An older application cannot represent partial/discount lines. Preserve data
    # by refusing that downgrade instead of deleting lines or inventing amounts.
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM receipt_items WHERE amount IS NULL OR amount <= 0) THEN
            RAISE EXCEPTION 'Cannot downgrade while partial or discount receipt lines exist';
        END IF;
    END $$""")
    op.drop_constraint("ck_receipt_item_draft_amount", "receipt_items", type_="check")
    op.alter_column("receipt_items", "amount", existing_type=sa.BigInteger(), nullable=False)
    op.create_check_constraint("receipt_items_check", "receipt_items", "amount > 0 and confidence between 0 and 100")
