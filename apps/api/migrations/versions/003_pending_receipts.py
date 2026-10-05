"""Keep confident, unconfirmed receipts discoverable in the Review Inbox."""

from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"


def upgrade():
    op.drop_constraint("review_tasks_kind_check", "review_tasks", type_="check")
    op.create_check_constraint(
        "ck_review_task_kind", "review_tasks", "kind in ('classification','extraction','duplicate','unallocated','confirmation')"
    )
    op.execute(
        sa.text("""
        INSERT INTO review_tasks (id, household_id, kind, title, receipt_id, resolved, created_at, updated_at, created_by)
        SELECT gen_random_uuid()::text, r.household_id, 'confirmation', COALESCE(NULLIF(r.merchant,''),'Paragon do zatwierdzenia'),
               r.id, false, now(), now(), r.created_by
        FROM receipts r WHERE r.status != 'confirmed'
        AND NOT EXISTS (SELECT 1 FROM review_tasks t WHERE t.receipt_id = r.id AND NOT t.resolved)
    """)
    )


def downgrade():
    # Preserve outstanding work within the previous schema's extraction task kind.
    op.execute(sa.text("UPDATE review_tasks SET kind='extraction' WHERE kind='confirmation'"))
    op.drop_constraint("ck_review_task_kind", "review_tasks", type_="check")
    op.create_check_constraint(
        "review_tasks_kind_check", "review_tasks", "kind in ('classification','extraction','duplicate','unallocated')"
    )
