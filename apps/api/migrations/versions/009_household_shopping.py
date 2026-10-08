"""Shared shopping lists, immutable purchase history and inventory batches."""

from alembic import op
import sqlalchemy as sa

revision = "009"
down_revision = "008"


def columns():
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("household_id", sa.String(36), sa.ForeignKey("households.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(36)),
        sa.Column("updated_by", sa.String(36)),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("quantity", sa.BigInteger(), nullable=False),
        sa.Column("unit", sa.String(12), nullable=False),
        sa.Column("location", sa.String(12), nullable=False),
        sa.CheckConstraint("unit in ('szt','kg','g','l','ml','opak')"),
        sa.CheckConstraint("location in ('fridge','freezer','pantry','cupboard')"),
    ]


def upgrade():
    op.create_table(
        "inventory_items",
        *columns(),
        sa.Column("expires_on", sa.Date(), nullable=True),
        sa.Column("minimum", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("quantity between 0 and 1000000000 and minimum between 0 and 1000000000"),
    )
    op.create_index("ix_inventory_items_household_id", "inventory_items", ["household_id"])
    op.create_table(
        "shopping_items",
        *columns(),
        sa.Column("estimated_amount", sa.BigInteger(), nullable=True),
        sa.Column("category_id", sa.String(36), sa.ForeignKey("categories.id"), nullable=True),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("purchased_on", sa.Date(), nullable=True),
        sa.Column("actual_amount", sa.BigInteger(), nullable=True),
        sa.Column("merchant", sa.String(120), nullable=False),
        sa.Column("receipt_item_id", sa.String(36), sa.ForeignKey("receipt_items.id"), nullable=True, unique=True),
        sa.Column("inventory_id", sa.String(36), sa.ForeignKey("inventory_items.id", ondelete="SET NULL"), nullable=True),
        sa.CheckConstraint("quantity between 1 and 1000000000"),
        sa.CheckConstraint("estimated_amount is null or estimated_amount between 0 and 100000000000"),
        sa.CheckConstraint("actual_amount is null or actual_amount between 0 and 100000000000"),
        sa.CheckConstraint("(status = 'pending' and purchased_on is null) or (status = 'bought' and purchased_on is not null)"),
    )
    op.create_index("ix_shopping_items_household_id", "shopping_items", ["household_id"])
    op.create_index("ix_shopping_items_history", "shopping_items", ["household_id", "status", "purchased_on"])


def downgrade():
    op.execute(
        """DO $$ BEGIN IF EXISTS(SELECT 1 FROM shopping_items) OR EXISTS(SELECT 1 FROM inventory_items) THEN RAISE EXCEPTION 'Cannot discard shopping history or household inventory'; END IF; END $$"""
    )
    op.drop_table("shopping_items")
    op.drop_table("inventory_items")
