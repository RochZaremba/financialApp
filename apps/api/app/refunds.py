"""Refunds preserve the original purchase, cash movement and exact category totals."""

from datetime import date, datetime, timedelta, timezone
import re

from fastapi import HTTPException
from pydantic import Field
from sqlalchemy import delete, func, select

from .domain import audit, fingerprint, normalize, pln_account, scoped
from .models import BankEntry, Mutation, Receipt, Transaction, TransactionAllocation
from .money import divide_money
from .schemas import PositiveMoney, Schema, TransactionInput
from .settlements import ensure_open


class RefundInput(Schema):
    amount: PositiveMoney
    date: date
    account_id: str
    description: str = Field(min_length=1, max_length=160)
    expected_updated_at: datetime


def refunded_amount(db, original_id, exclude_id=None):
    query = select(func.coalesce(func.sum(Transaction.amount), 0)).where(Transaction.refund_of_id == original_id)
    if exclude_id:
        query = query.where(Transaction.id != exclude_id)
    return int(db.scalar(query))


def refund_allocations(db, original, actor):
    """Rebuild proportional partial refunds against remaining category grosze."""
    rows = list(
        db.scalars(
            select(TransactionAllocation)
            .where(TransactionAllocation.transaction_id == original.id)
            .order_by(TransactionAllocation.category_id)
        )
    )
    remaining = [r.amount for r in rows]
    refunds = list(
        db.scalars(select(Transaction).where(Transaction.refund_of_id == original.id).order_by(Transaction.date, Transaction.id))
    )
    for refund in refunds:
        shares = divide_money(refund.amount, remaining) if rows else []
        if any(share > available for share, available in zip(shares, remaining, strict=True)):
            raise HTTPException(422, "Suma zwrotów przekracza koszt zakupu.")
        old = list(db.scalars(select(TransactionAllocation).where(TransactionAllocation.transaction_id == refund.id)))
        wanted = {row.category_id: share for row, share in zip(rows, shares, strict=True) if share}
        if {r.category_id: r.amount for r in old} != wanted or refund.status != ("categorized" if rows else "unallocated"):
            ensure_open(db, original.household_id, refund.date.strftime("%Y-%m"))
            db.execute(delete(TransactionAllocation).where(TransactionAllocation.transaction_id == refund.id))
            for category_id, amount in wanted.items():
                db.add(
                    TransactionAllocation(
                        household_id=original.household_id,
                        transaction_id=refund.id,
                        category_id=category_id,
                        amount=amount,
                        created_by=actor,
                    )
                )
            refund.status = "categorized" if rows else "unallocated"
            refund.updated_at, refund.updated_by = datetime.now(timezone.utc), actor
        remaining = [available - share for share, available in zip(shares, remaining, strict=True)] if rows else []
    db.flush()


def create_refund(db, member, original, data, key, *, existing=None, source="manual", source_id=None, allow_edit=False):
    from .domain import create_transaction

    signature = fingerprint("refund:" + original.id, data.model_dump(mode="json"))
    old = db.scalar(select(Mutation).where(Mutation.household_id == member.household_id, Mutation.key == key))
    if old:
        if old.request_hash != signature or old.resource != "refund":
            raise HTTPException(409, "Ten zwrot zapisano już z innymi danymi.")
        return scoped(db, Transaction, member.household_id, old.entity_id)
    if original.household_id != member.household_id or original.kind != "expense":
        raise HTTPException(422, "Zwrot musi dotyczyć wydatku z tego domu.")
    if original.updated_at != data.expected_updated_at:
        raise HTTPException(409, "Zakup lub jego zwroty zmieniły się. Odśwież dane.")
    ensure_open(db, member.household_id, data.date.strftime("%Y-%m"))
    pln_account(db, member.household_id, data.account_id)
    if data.date < original.date or data.amount + refunded_amount(db, original.id, existing.id if existing else None) > original.amount:
        raise HTTPException(422, "Zwrot nie może poprzedzać zakupu ani przekroczyć jego pozostałej kwoty.")
    if existing:
        if existing.kind != "income" or (
            not allow_edit and (existing.amount != data.amount or existing.account_id != data.account_id or existing.date != data.date)
        ):
            raise HTTPException(422, "Zwrot nie pasuje do wpływu bankowego.")
        if existing.refund_of_id and existing.refund_of_id != original.id:
            raise HTTPException(409, "Wpływ jest już zwrotem do innego zakupu.")
        tx = existing
        if allow_edit:
            if existing.source == "bank" or db.scalar(select(BankEntry.id).where(BankEntry.transaction_id == existing.id)):
                raise HTTPException(422, "Kwota, data i konto zwrotu są uzgodnione z bankiem.")
            tx.amount, tx.date, tx.account_id = data.amount, data.date, data.account_id
        tx.description = data.description
    else:
        tx = create_transaction(
            db,
            member,
            TransactionInput(kind="income", amount=data.amount, date=data.date, account_id=data.account_id, description=data.description),
            key,
            source=source,
            source_id=source_id,
        )
    tx.refund_of_id = original.id
    tx.updated_by = member.user_id
    original.updated_at, original.updated_by = datetime.now(timezone.utc), member.user_id
    db.flush()
    refund_allocations(db, original, member.user_id)
    db.add(
        Mutation(
            household_id=member.household_id, key=key, resource="refund", request_hash=signature, entity_id=tx.id, created_by=member.user_id
        )
    )
    if not allow_edit:
        audit(db, member, "refund.created", tx.id)
    return tx


def protect_refunded_purchase(db, tx, movement):
    if tx.refund_of_id:
        linked = tx.source == "bank" or db.scalar(select(BankEntry.id).where(BankEntry.transaction_id == tx.id))
        if (
            movement.kind != "income"
            or movement.destination_id
            or movement.allocations
            or (linked and any(getattr(tx, name) != getattr(movement, name) for name in ("amount", "date", "account_id")))
        ):
            raise HTTPException(422, "Zwrot musi pozostać zgodny z zakupem i bankiem. Podział wynika z oryginalnego zakupu.")
    elif refunded_amount(db, tx.id) and any(
        getattr(tx, name) != getattr(movement, name) for name in ("amount", "date", "account_id", "kind")
    ):
        raise HTTPException(422, "Zakup ma już zwroty. Jego kwota, data i konto muszą pozostać zgodne ze zwrotami.")


def refund_candidates(db, household_id, amount, day, *, account_id=None, automatic=False, description="", exclude_refund_id=None):
    returned = select(Transaction.refund_of_id.label("original_id"), func.sum(Transaction.amount).label("amount")).where(
        Transaction.household_id == household_id, Transaction.refund_of_id.is_not(None)
    )
    if exclude_refund_id:
        returned = returned.where(Transaction.id != exclude_refund_id)
    returned = returned.group_by(Transaction.refund_of_id).subquery()
    remainder = Transaction.amount - func.coalesce(returned.c.amount, 0)
    query = (
        select(Transaction, remainder.label("remaining"))
        .outerjoin(returned, returned.c.original_id == Transaction.id)
        .where(
            Transaction.household_id == household_id,
            Transaction.kind == "expense",
            remainder >= amount,
            Transaction.date <= day,
            Transaction.date >= day - timedelta(days=90),
        )
        .order_by(Transaction.date.desc())
        .limit(201)
    )
    if account_id:
        query = query.where(Transaction.account_id == account_id)
    result = []
    for tx, remaining in db.execute(query):
        remaining = int(remaining)
        if automatic:
            names = [tx.description]
            names += list(db.scalars(select(Receipt.merchant).where(Receipt.transaction_id == tx.id)))
            names += list(db.scalars(select(BankEntry.description).where(BankEntry.transaction_id == tx.id, BankEntry.amount < 0)))
            if not any(same_merchant(description, name) for name in names):
                continue
            if remaining != amount and not re.search(r"\b(zwrot|refund|refundacja|return|reversal|korekta)\b", normalize(description)):
                continue
        result.append((tx, remaining))
    return result


def same_merchant(first, second):
    noise = {
        "blik",
        "zakup",
        "nfc",
        "zwrot",
        "refund",
        "return",
        "reversal",
        "platnosc",
        "transakcja",
        "karta",
        "karty",
        "polska",
        "poland",
        "uznanie",
        "obciazenie",
        "operacja",
        "bankowa",
        "sklep",
        "restauracja",
        "spolka",
        "limited",
        "platnosci",
        "korekta",
        "terminal",
    }

    def parts(value):
        return [p for p in re.findall(r"[a-z]+", normalize(value)) if p not in noise and len(p) >= 3]

    a, b = parts(first), parts(second)
    if any(p in b for p in a if len(p) >= 4):
        return True
    x, y = "".join(a), "".join(b)
    return (len(x) >= 3 and x == y) or (min(len(x), len(y)) >= 7 and (x in y or y in x))
