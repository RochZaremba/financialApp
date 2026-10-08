import calendar
import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from datetime import date, datetime

from fastapi import HTTPException
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from .config import WARSAW
from .models import (
    Account,
    Audit,
    BudgetAllocation,
    Category,
    ClassificationRule,
    Goal,
    IncomeSource,
    Member,
    Period,
    Recurring,
    Transaction,
    TransactionAllocation,
)
from .schemas import TransactionInput


def today():
    return datetime.now(WARSAW).date()


def month_valid(month: str):
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month) or not 2000 <= int(month[:4]) <= 2100:
        raise HTTPException(422, "Miesiąc musi mieć format RRRR-MM (2000–2100).")
    return month


def month_dates(month: str):
    month_valid(month)
    y, m = map(int, month.split("-"))
    return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])


def scoped(db: Session, model, household_id: str, object_id: str, lock: bool = False):
    query = select(model).where(model.id == object_id, model.household_id == household_id)
    if lock:
        query = query.with_for_update()
    record = db.scalar(query)
    if not record:
        raise HTTPException(404, "Nie znaleziono danych.")
    return record


def records(db: Session, model, household_id: str):
    return list(db.scalars(select(model).where(model.household_id == household_id).order_by(model.created_at)))


def serialize(record):
    return {
        c.name: getattr(record, c.name)
        for c in record.__table__.columns
        if c.name not in ("password_hash", "path", "token_hash", "request_hash")
    }


def audit(db, member, action, entity_id):
    db.add(Audit(household_id=member.household_id, created_by=member.user_id, action=action, entity_id=entity_id))


def normalize(text: str):
    return re.sub(
        r"\s+", " ", "".join(c for c in unicodedata.normalize("NFKD", text.casefold().replace("ł", "l")) if not unicodedata.combining(c))
    ).strip()


def classify(db, household_id, name, merchant, *, rules=None, active=None):
    if rules is None:
        rules = records(db, ClassificationRule, household_id)
    if active is None:
        active = {c.id for c in records(db, Category, household_id) if not c.archived}
    for kind, pattern in [("exact", name), ("normalized", normalize(name)), ("merchant", normalize(merchant))]:
        found = next((r for r in rules if r.kind == kind and r.pattern == pattern and r.category_id in active), None)
        if found:
            return found.category_id, 100
    return None, 0


def learn(db, household_id, name, category_id, user_id):
    pattern = normalize(name)
    rule = db.scalar(
        select(ClassificationRule).where(
            ClassificationRule.household_id == household_id, ClassificationRule.kind == "normalized", ClassificationRule.pattern == pattern
        )
    )
    if rule:
        rule.category_id = category_id
        rule.updated_by = user_id
    else:
        db.add(
            ClassificationRule(household_id=household_id, pattern=pattern, kind="normalized", category_id=category_id, created_by=user_id)
        )


def pln_account(db, household_id, account_id):
    account = scoped(db, Account, household_id, account_id)
    if account.currency != "PLN":
        raise HTTPException(422, "Transakcje budżetu zapisujemy w złotych. Wybierz konto PLN.")
    return account


def create_transaction(db: Session, member: Member, data: TransactionInput, key: str, source="manual", source_id=None):
    # Serializes duplicate submissions and budget-affecting writes within one household.
    from .models import Household

    db.scalar(select(Household).where(Household.id == member.household_id).with_for_update())
    fingerprint = hashlib.sha256(json.dumps(data.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()
    existing = db.scalar(select(Transaction).where(Transaction.household_id == member.household_id, Transaction.idempotency_key == key))
    if existing:
        if existing.request_hash != fingerprint:
            raise HTTPException(409, "Ten zapis już istnieje z innymi danymi. Odśwież formularz.")
        return existing
    pln_account(db, member.household_id, data.account_id)
    if data.date.year < 2000 or data.date.year > 2100:
        raise HTTPException(422, "Wybierz datę pomiędzy 2000 a 2100 rokiem.")
    if data.destination_id:
        pln_account(db, member.household_id, data.destination_id)
        if data.destination_id == data.account_id:
            raise HTTPException(422, "Wybierz dwa różne konta.")
    if data.kind in ("transfer", "saving") and not data.destination_id:
        raise HTTPException(422, "Wybierz konto docelowe.")
    if data.kind not in ("transfer", "saving") and data.destination_id:
        raise HTTPException(422, "Ten rodzaj transakcji nie ma konta docelowego.")
    if data.kind == "pocket":
        if not data.member_id:
            raise HTTPException(422, "Wybierz osobę, która otrzyma kieszonkowe.")
        scoped(db, Member, member.household_id, data.member_id)
    elif data.member_id:
        raise HTTPException(422, "Odbiorca jest dostępny tylko dla kieszonkowego.")
    if data.kind == "saving":
        if not data.goal_id:
            raise HTTPException(422, "Wybierz cel oszczędnościowy.")
        scoped(db, Goal, member.household_id, data.goal_id)
    elif data.goal_id:
        raise HTTPException(422, "Cel jest dostępny tylko dla oszczędności.")
    if data.kind == "expense":
        if data.allocations and sum(a.amount for a in data.allocations) != data.amount:
            raise HTTPException(422, "Suma kategorii musi być równa kwocie wydatku.")
        if len({a.category_id for a in data.allocations}) != len(data.allocations):
            raise HTTPException(422, "Każda kategoria może wystąpić tylko raz.")
        for allocation in data.allocations:
            category = scoped(db, Category, member.household_id, allocation.category_id)
            if category.archived:
                raise HTTPException(422, "Ta kategoria została zarchiwizowana.")
    elif data.allocations:
        raise HTTPException(422, "Tylko wspólne wydatki wymagają kategorii.")
    payload = data.model_dump(exclude={"allocations"})
    transaction = Transaction(
        **payload,
        household_id=member.household_id,
        idempotency_key=key,
        request_hash=fingerprint,
        status="unallocated" if data.kind == "expense" and not data.allocations else "categorized",
        source=source,
        source_id=source_id,
        created_by=member.user_id,
    )
    db.add(transaction)
    db.flush()
    for allocation in data.allocations:
        db.add(
            TransactionAllocation(
                **allocation.model_dump(), transaction_id=transaction.id, household_id=member.household_id, created_by=member.user_id
            )
        )
    if transaction.status == "unallocated":
        from .models import ReviewTask

        db.add(
            ReviewTask(
                household_id=member.household_id,
                transaction_id=transaction.id,
                kind="unallocated",
                title=data.description,
                created_by=member.user_id,
            )
        )
    audit(db, member, "transaction.created", transaction.id)
    return transaction


def transaction_data(db, tx):
    data = serialize(tx)
    data["allocations"] = [
        serialize(a)
        for a in db.scalars(
            select(TransactionAllocation).where(
                TransactionAllocation.transaction_id == tx.id, TransactionAllocation.household_id == tx.household_id
            )
        )
    ]
    return data


def budget_data(db, household_id, month):
    start, end = month_dates(month)
    period = db.scalar(select(Period).where(Period.household_id == household_id, Period.month == month))
    txs = list(
        db.scalars(select(Transaction).where(Transaction.household_id == household_id, Transaction.date >= start, Transaction.date <= end))
    )
    used = defaultdict(int)
    unallocated = 0
    category_totals = db.execute(
        select(TransactionAllocation.category_id, func.sum(TransactionAllocation.amount))
        .join(Transaction, Transaction.id == TransactionAllocation.transaction_id)
        .where(
            TransactionAllocation.household_id == household_id,
            Transaction.household_id == household_id,
            Transaction.kind == "expense",
            Transaction.date >= start,
            Transaction.date <= end,
        )
        .group_by(TransactionAllocation.category_id)
    )
    for category_id, amount in category_totals:
        used[("category", category_id)] = int(amount)
    for tx in txs:
        if tx.kind == "expense":
            if tx.status == "unallocated":
                unallocated += tx.amount
        elif tx.kind == "pocket":
            used[("pocket", tx.member_id)] += tx.amount
        elif tx.kind == "saving":
            used[("goal", tx.goal_id)] += tx.amount
    allocations = []
    seen = set()
    if period:
        for a in db.scalars(select(BudgetAllocation).where(BudgetAllocation.period_id == period.id)):
            data = serialize(a)
            data["spent"] = used[(a.kind, a.reference_id)]
            data["remaining"] = a.amount - data["spent"]
            allocations.append(data)
            seen.add((a.kind, a.reference_id))
    # Actual spending remains visible even if that envelope was not planned.
    for (kind, reference), amount in used.items():
        if (kind, reference) in seen:
            continue
        if kind == "category":
            item = scoped(db, Category, household_id, reference)
            label, group = item.name, item.group
        elif kind == "goal":
            item = scoped(db, Goal, household_id, reference)
            label, group = item.name, "Przyszłość"
        else:
            from .models import User

            item = scoped(db, Member, household_id, reference)
            label, group = db.get(User, item.user_id).name, "Kieszonkowe"
        allocations.append(
            dict(
                id=f"actual-{reference}",
                kind=kind,
                reference_id=reference,
                label=label,
                group=group,
                amount=0,
                spent=amount,
                remaining=-amount,
            )
        )
    planned = period.planned_income if period else 0
    sources = (
        [
            serialize(source)
            for source in db.scalars(
                select(IncomeSource)
                .where(IncomeSource.household_id == household_id, IncomeSource.period_id == period.id)
                .order_by(IncomeSource.position)
            )
        ]
        if period
        else []
    )
    # An older deployed client/server may update the legacy total during rollback.
    # Keep that authoritative total visible without inventing personal attribution.
    if sum(source["amount"] for source in sources) != planned:
        sources = [dict(id=f"legacy-{period.id}", name="Dochód wspólny", member_id=None, amount=planned)]
    assigned = sum(a["amount"] for a in allocations)
    expenses = sum(t.amount for t in txs if t.kind == "expense")
    pocket = sum(t.amount for t in txs if t.kind == "pocket")
    savings = sum(t.amount for t in txs if t.kind == "saving")
    return dict(
        period=serialize(period) if period else None,
        month=month,
        planned_income=planned,
        income_sources=sources,
        assigned=assigned,
        unassigned=planned - assigned,
        spent=expenses + pocket + savings,
        expenses=expenses,
        pocket=pocket,
        savings=savings,
        income=sum(t.amount for t in txs if t.kind == "income"),
        remaining=planned - expenses - pocket - savings,
        unallocated=unallocated,
        allocations=allocations,
    )


def account_data(db, household_id):
    accounts = records(db, Account, household_id)
    balances = {a.id: a.opening_balance for a in accounts}
    outgoing = db.execute(
        select(Transaction.account_id, func.sum(case((Transaction.kind == "income", Transaction.amount), else_=-Transaction.amount)))
        .where(Transaction.household_id == household_id)
        .group_by(Transaction.account_id)
    )
    incoming = db.execute(
        select(Transaction.destination_id, func.sum(Transaction.amount))
        .where(Transaction.household_id == household_id, Transaction.destination_id.is_not(None))
        .group_by(Transaction.destination_id)
    )
    for account_id, amount in list(outgoing) + list(incoming):
        balances[account_id] += int(amount)
    return [dict(**serialize(a), balance=balances[a.id]) for a in accounts]


def goal_data(db, household_id):
    goals = records(db, Goal, household_id)
    result = []
    for goal in goals:
        current = goal.opening_amount + int(
            db.scalar(
                select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                    Transaction.household_id == household_id, Transaction.goal_id == goal.id, Transaction.kind == "saving"
                )
            )
            or 0
        )
        months = max(0, (goal.target - current + goal.monthly_amount - 1) // goal.monthly_amount) if goal.monthly_amount else None
        target_date = None
        if months is not None:
            index = today().year * 12 + today().month - 1 + months
            target_date = date(index // 12, index % 12 + 1, 1).isoformat() if index // 12 <= 9999 else None
        result.append(dict(**serialize(goal), current=current, estimated_date=target_date))
    return result


def recurring_data(db, household_id, month):
    start, end = month_dates(month)
    result = []
    for row in records(db, Recurring, household_id):
        paid = db.scalar(
            select(Transaction.id).where(
                Transaction.household_id == household_id,
                Transaction.source == "recurring",
                Transaction.source_id == row.id,
                Transaction.date >= start,
                Transaction.date <= end,
            )
        )
        result.append(dict(**serialize(row), paid=bool(paid), due_date=date(start.year, start.month, min(row.day, end.day)).isoformat()))
    return result


def fingerprint(resource, data):
    return hashlib.sha256(json.dumps({"resource": resource, "data": data}, sort_keys=True).encode()).hexdigest()


def create_record(db, member, model, data, key):
    from .models import Household, Mutation

    db.scalar(select(Household).where(Household.id == member.household_id).with_for_update())
    signature = fingerprint(model.__tablename__, data)
    old = db.scalar(select(Mutation).where(Mutation.household_id == member.household_id, Mutation.key == key))
    if old:
        if old.request_hash != signature:
            raise HTTPException(409, "Ten zapis już istnieje z innymi danymi. Odśwież formularz.")
        return scoped(db, model, member.household_id, old.entity_id)
    row = model(**data, household_id=member.household_id, created_by=member.user_id)
    db.add(row)
    db.flush()
    db.add(
        Mutation(
            household_id=member.household_id,
            key=key,
            resource=model.__tablename__,
            request_hash=signature,
            entity_id=row.id,
            created_by=member.user_id,
        )
    )
    audit(db, member, model.__tablename__ + ".created", row.id)
    return row
