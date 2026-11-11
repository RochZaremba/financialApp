"""Local one-to-one matching. Never contacts a bank or changes fetch limits."""

from collections import Counter
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import and_, delete, func, or_, select

from .bank_provider import load_config
from .config import WARSAW
from .domain import audit
from .models import Audit, BankAccount, BankEntry, Household, Member, Receipt, ReviewTask, Transaction, TransactionAllocation
from .refunds import RefundInput, create_refund, refund_candidates, refunded_amount
from .settlements import ensure_open


def link(db, entry, tx, actor, method="unique"):
    entry.transaction_id, entry.reviewed, entry.match_method = tx.id, True, method
    entry.updated_by, entry.updated_at = actor.user_id, datetime.now(timezone.utc)
    audit(db, actor, "bank.auto_refund" if method == "refund" else "bank.auto_matched", entry.id)


def reconcile(db, member, cfg, *, new_expenses=()):
    from .bank_sync import matches, register_expense

    db.scalar(select(Household).where(Household.id == cfg.household_id).with_for_update())
    if (
        member.household_id != cfg.household_id
        or member.user_id not in cfg.allowed_users
        or not db.scalar(select(Member.id).where(Member.household_id == cfg.household_id, Member.user_id == member.user_id))
    ):
        raise HTTPException(403, "Brak dostępu do uzgadniania banku.")
    accounts = {a.id: a for a in db.scalars(select(BankAccount).where(BankAccount.household_id == cfg.household_id))}
    entries = list(
        db.scalars(
            select(BankEntry)
            .where(
                BankEntry.household_id == cfg.household_id,
                or_(
                    BankEntry.reviewed.is_(False),
                    and_(BankEntry.match_method.is_(None), BankEntry.amount > 0, BankEntry.transaction_id.is_not(None)),
                ),
            )
            .order_by(BankEntry.date, BankEntry.id)
            .limit(2000)
        )
    )
    candidates, placeholders = {}, {}
    for entry in entries:
        account = accounts.get(entry.bank_account_id)
        if not account or not account.account_id:
            continue
        if not entry.transaction_id:
            candidates[entry.id] = matches(db, entry, account, automatic=True)
            continue
        tx = db.get(Transaction, entry.transaction_id)
        if tx and tx.source == "bank" and tx.kind == "expense" and tx.status == "unallocated" and not refunded_amount(db, tx.id):
            if (
                db.scalar(select(Receipt.id).where(Receipt.transaction_id == tx.id))
                or db.scalar(select(func.count()).select_from(BankEntry).where(BankEntry.transaction_id == tx.id)) != 1
            ):
                continue
            possible = [t for t in matches(db, entry, account, automatic=True) if t.id != tx.id and t.source != "bank"]
            candidates[entry.id], placeholders[entry.id] = possible, tx
    reverse = Counter((tx.id, entry.bank_account_id) for entry in entries for tx in candidates.get(entry.id, []))
    matched = 0
    for entry in entries:
        possible = candidates.get(entry.id, [])
        if len(possible) != 1 or reverse[(possible[0].id, entry.bank_account_id)] != 1:
            continue
        target = possible[0]
        old = placeholders.get(entry.id)
        if old:
            try:
                ensure_open(db, cfg.household_id, old.date.strftime("%Y-%m"))
                ensure_open(db, cfg.household_id, target.date.strftime("%Y-%m"))
            except HTTPException:
                continue
            old_id = old.id
            link(db, entry, target, member)
            db.flush()
            db.execute(delete(ReviewTask).where(ReviewTask.transaction_id == old_id, ReviewTask.household_id == cfg.household_id))
            db.execute(delete(TransactionAllocation).where(TransactionAllocation.transaction_id == old_id))
            db.delete(old)
            db.add(
                Audit(
                    household_id=cfg.household_id,
                    created_by=member.user_id,
                    action="bank.placeholder_merged",
                    entity_id=entry.id,
                    details={"replaced_id": old_id, "kept_id": target.id},
                )
            )
        else:
            link(db, entry, target, member)
        matched += 1
    db.flush()
    for entry in entries:
        if entry.transaction_id or entry.id not in new_expenses:
            continue
        register_expense(db, cfg, accounts[entry.bank_account_id], entry, member)
    db.flush()
    refunded = 0
    refund_pairs = {}
    for entry in entries:
        existing = db.get(Transaction, entry.transaction_id) if entry.transaction_id else None
        legacy_income = bool(
            existing
            and existing.kind == "income"
            and not existing.refund_of_id
            and existing.source == "bank"
            and entry.match_method is None
        )
        if (
            entry.amount <= 0
            or not entry.reliable
            or (entry.transaction_id and not legacy_income)
            or (not legacy_income and not entry.auto_refund_eligible)
        ):
            continue
        account = accounts.get(entry.bank_account_id)
        if not account or not account.account_id or entry.date < account.created_at.astimezone(WARSAW).date():
            continue
        if entry.counterparty_hash and any(a.iban_hash == entry.counterparty_hash for a in accounts.values()):
            continue
        if candidates.get(entry.id):
            continue
        possible = refund_candidates(
            db, cfg.household_id, entry.amount, entry.date, account_id=account.account_id, automatic=True, description=entry.description
        )
        if len(possible) != 1:
            continue
        refund_pairs[entry.id] = possible[0]
    claimed = Counter()
    for entry in entries:
        if entry.id in refund_pairs:
            claimed[refund_pairs[entry.id][0].id] += entry.amount
    for entry in entries:
        if entry.id not in refund_pairs:
            continue
        original, available = refund_pairs[entry.id]
        account = accounts[entry.bank_account_id]
        if claimed[original.id] > available:
            continue
        try:
            with db.begin_nested():
                tx = create_refund(
                    db,
                    member,
                    original,
                    RefundInput(
                        amount=entry.amount,
                        date=entry.date,
                        account_id=account.account_id,
                        description=entry.description,
                        expected_updated_at=original.updated_at,
                    ),
                    "bank-refund:" + entry.id,
                    source="bank",
                    source_id=entry.id,
                    existing=db.get(Transaction, entry.transaction_id) if entry.transaction_id else None,
                )
                link(db, entry, tx, member, "refund")
        except HTTPException:
            continue
        refunded += 1
    db.flush()
    return dict(matched=matched, refunds=refunded)


def maybe_reconcile(db, member):
    cfg = load_config()
    if cfg and cfg.household_id == member.household_id and member.user_id in cfg.allowed_users:
        return reconcile(db, member, cfg)
    return dict(matched=0, refunds=0)


def reconcile_background(cfg):
    from .db import SessionLocal

    with SessionLocal() as db:
        member = db.scalar(
            select(Member).where(Member.household_id == cfg.household_id, Member.user_id == cfg.owner_id, Member.role == "owner")
        )
        if member:
            reconcile(db, member, cfg)
            db.commit()
