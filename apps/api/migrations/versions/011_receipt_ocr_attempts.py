"""Durable OCR proposals and safe provider diagnostics."""

from alembic import op
import sqlalchemy as sa

revision = "011"
down_revision = "010"


def upgrade():
    op.create_table(
        "receipt_ocr_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("household_id", sa.String(36), sa.ForeignKey("households.id", ondelete="CASCADE"), nullable=False),
        sa.Column("receipt_id", sa.String(36), sa.ForeignKey("receipts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(36)),
        sa.Column("updated_by", sa.String(36)),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("diagnostics", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("receipt_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("receipt_id", "key"),
        sa.CheckConstraint("status in ('succeeded','partial','failed')"),
    )
    op.create_index("ix_receipt_ocr_attempts_household_id", "receipt_ocr_attempts", ["household_id"])
    op.create_index("ix_receipt_ocr_attempts_receipt_id", "receipt_ocr_attempts", ["receipt_id"])


def downgrade():
    op.execute(
        """DO $$ BEGIN IF EXISTS(SELECT 1 FROM receipt_ocr_attempts) THEN RAISE EXCEPTION 'Cannot discard OCR history'; END IF; END $$"""
    )
    op.drop_table("receipt_ocr_attempts")
