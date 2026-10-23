"""Read-only household entry counts by original recorder, never by payer."""

from datetime import datetime, time, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import WARSAW
from .db import get_db
from .domain import month_dates
from .models import Member, Receipt, Transaction, User
from .security import household_member

router = APIRouter(tags=["activity"])


def empty_counts():
    return dict(receipts=0, expenses=0, expense_amount=0, incomes=0, income_amount=0)


@router.get("/households/{household_id}/activity")
def activity(
    household_id: str,
    member: Annotated[Member, Depends(household_member)],
    db: Annotated[Session, Depends(get_db)],
    month: str | None = None,
):
    start = end = None
    if month is not None:
        first, last = month_dates(month)
        start = datetime.combine(first, time.min, WARSAW)
        end = datetime.combine(last + timedelta(days=1), time.min, WARSAW)

    def bounded(query, model):
        query = query.where(model.household_id == household_id)
        if start is not None:
            query = query.where(model.created_at >= start, model.created_at < end)
        return query

    members = dict(
        db.execute(select(Member.user_id, User.name).join(User, User.id == Member.user_id).where(Member.household_id == household_id)).all()
    )
    people = {
        identifier: dict(user_id=identifier, name=name, current_member=True, **empty_counts()) for identifier, name in members.items()
    }

    def person(identifier, name):
        if identifier not in people:
            people[identifier] = dict(user_id=identifier, name=name or "Nieznany autor", current_member=False, **empty_counts())
        return people[identifier]

    receipt_query = (
        select(User.id, User.name, func.count(Receipt.id))
        .select_from(Receipt)
        .outerjoin(User, User.id == Receipt.created_by)
        .group_by(User.id, User.name)
    )
    for identifier, name, count in db.execute(bounded(receipt_query, Receipt)):
        person(identifier, name)["receipts"] = count

    transaction_query = (
        select(User.id, User.name, Transaction.kind, func.count(Transaction.id), func.sum(Transaction.amount))
        .select_from(Transaction)
        .outerjoin(User, User.id == Transaction.created_by)
        .where(Transaction.kind.in_(["expense", "income"]))
        .group_by(User.id, User.name, Transaction.kind)
    )
    for identifier, name, kind, count, amount in db.execute(bounded(transaction_query, Transaction)):
        row = person(identifier, name)
        count_field, amount_field = ("expenses", "expense_amount") if kind == "expense" else ("incomes", "income_amount")
        row[count_field] = count
        row[amount_field] = int(amount)

    totals = {field: sum(row[field] for row in people.values()) for field in empty_counts()}
    return dict(
        month=month,
        totals=totals,
        people=sorted(people.values(), key=lambda row: (row["user_id"] is None, row["name"].casefold(), row["user_id"] or "")),
    )
