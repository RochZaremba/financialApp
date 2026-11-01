"""Durable booked movements, conservative reconciliation and private push outbox."""

import json
import logging
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException
from pywebpush import WebPushException, webpush
from sqlalchemy import delete, or_, select
from sqlalchemy.exc import SQLAlchemyError

from .bank_diagnostics import failure_diagnostic
from .bank_provider import BankError, EnableBanking, minor_amount, movement, push_url_allowed
from .config import WARSAW
from .db import SessionLocal
from .domain import audit, create_transaction
from .models import BankAccount, BankConnection, BankDelivery, BankEntry, BankSubscription, Household, Member, Transaction
from .schemas import TransactionInput
from .security import digest


def now():
    return datetime.now(timezone.utc)


def matches(db, entry, account):
    if not account.account_id:
        return []
    if entry.amount < 0:
        account_match = (Transaction.account_id == account.account_id) & Transaction.kind.in_(["expense", "pocket", "saving", "transfer"])
    else:
        account_match = or_(
            (Transaction.account_id == account.account_id) & (Transaction.kind == "income"),
            (Transaction.destination_id == account.account_id) & Transaction.kind.in_(["saving", "transfer"]),
        )
    linked = (
        select(BankEntry.id)
        .where(BankEntry.transaction_id == Transaction.id, BankEntry.bank_account_id == entry.bank_account_id, BankEntry.id != entry.id)
        .exists()
    )
    return list(
        db.scalars(
            select(Transaction)
            .where(
                Transaction.household_id == entry.household_id,
                Transaction.amount == abs(entry.amount),
                Transaction.date >= entry.date - timedelta(days=7),
                Transaction.date <= entry.date + timedelta(days=7),
                account_match,
                ~linked,
            )
            .order_by(Transaction.date.desc())
            .limit(100)
        )
    )


def matches_account(tx, amount, account_id):
    if amount < 0:
        return tx.account_id == account_id and tx.kind in ("expense", "pocket", "saving", "transfer")
    return (tx.account_id == account_id and tx.kind == "income") or (tx.destination_id == account_id and tx.kind in ("saving", "transfer"))


def register_expense(db, cfg, account, entry, member):
    # Credits may be salary, refunds or own transfers: require an explicit classification.
    # History and entries without stable bank IDs also remain in the bank inbox.
    if entry.amount >= 0 or not entry.reliable or entry.date < account.created_at.astimezone(WARSAW).date() or matches(db, entry, account):
        return
    if entry.counterparty_hash and db.scalar(
        select(BankAccount.id).where(BankAccount.household_id == cfg.household_id, BankAccount.iban_hash == entry.counterparty_hash)
    ):
        return
    try:
        # No partial ledger writes on a closed-period or domain validation failure.
        with db.begin_nested():
            tx = create_transaction(
                db,
                member,
                TransactionInput(
                    kind="expense", amount=-entry.amount, date=entry.date, description=entry.description, account_id=account.account_id
                ),
                "bank:" + entry.id,
                source="bank",
                source_id=entry.id,
            )
            entry.transaction_id = tx.id
    except HTTPException:
        pass


def sync_connection(cfg, connection_id):
    with SessionLocal() as db:
        # Claim a durable lease with a short row lock; network calls hold no financial locks.
        connection = db.scalar(
            select(BankConnection)
            .where(BankConnection.id == connection_id, BankConnection.household_id == cfg.household_id)
            .with_for_update()
        )
        if not connection or connection.status != "active" or not connection.session_cipher:
            return False
        if connection.next_sync and connection.next_sync > now():
            return False
        member = db.scalar(select(Member).where(Member.household_id == cfg.household_id, Member.user_id == connection.user_id))
        if not member or member.role != "owner" or connection.user_id != cfg.owner_id:
            connection.status = "revoke_pending"
            db.commit()
            return False
        if connection.valid_until and connection.valid_until <= now():
            connection.status = "expired"
            connection.error_code = "EXPIRED_SESSION"
            db.commit()
            return False
        accounts = list(
            db.scalars(
                select(BankAccount).where(
                    BankAccount.connection_id == connection.id,
                    BankAccount.household_id == cfg.household_id,
                    BankAccount.account_id.is_not(None),
                    BankAccount.start_date.is_not(None),
                )
            )
        )
        if not accounts:
            return False
        lease_until = now() + timedelta(hours=6)
        connection.next_sync = lease_until
        # Durable six-hour lease before network I/O. A crashed job cannot immediately
        # refetch the bank, and no household/financial lock is held during HTTP calls.
        db.commit()
        started = time.monotonic()
        stage = "load_accounts"
        client = EnableBanking(cfg)
        try:
            # Fetch and validate ALL pages/accounts before mutating any bank/ledger data.
            batches = []
            for account in accounts:
                stage = "decrypt_account"
                uid = cfg.open(account.uid_cipher)
                stage = "fetch_transactions"
                raw = client.transactions(uid, account.start_date)
                stage = "parse_transactions"
                parsed = [row for row in (movement(item, account.currency) for item in raw) if row and row["date"] >= account.start_date]
                if any(row["date"] > date.today() + timedelta(days=1) for row in parsed):
                    raise BankError("INVALID_BANK_DATE")
                stage = "fetch_balances"
                balances = client.balances(uid)
                stage = "parse_balances"
                booked = [b for b in balances if b.get("balance_type") in ("ITBD", "CLBD")]
                chosen = next((b for b in booked if b.get("balance_type") == "ITBD"), next(iter(booked), None))
                balance = None
                if chosen:
                    if chosen["balance_amount"]["currency"] != account.currency:
                        raise BankError("CURRENCY_MISMATCH")
                    balance = minor_amount(chosen["balance_amount"]["amount"])
                batches.append((account, parsed, balance))
            stage = "authorize_write"
            db.scalar(select(Household).where(Household.id == cfg.household_id).with_for_update())
            db.refresh(connection, with_for_update=True)
            if connection.status != "active":
                return False
            # Membership may have changed while bank HTTP requests were in flight.
            member = db.scalar(
                select(Member).where(Member.household_id == cfg.household_id, Member.user_id == cfg.owner_id, Member.role == "owner")
            )
            if not member:
                connection.status = "revoke_pending"
                db.commit()
                return False
            with db.begin_nested():
                for account, parsed, balance in batches:
                    stage = "save_entries"
                    db.refresh(account)
                    if account.connection_id != connection.id:
                        raise BankError("CONNECTION_CHANGED")
                    initial_sync = account.last_sync is None
                    occurrences = Counter()
                    for row in parsed:
                        reference = row.pop("reference")
                        reliable = bool(reference)
                        if reference:
                            hashed = digest("reference:" + reference)
                        else:
                            signature = json.dumps(row, default=str, sort_keys=True)
                            occurrences[signature] += 1
                            hashed = digest(f"uncertain:{signature}:{occurrences[signature]}")
                        previous = db.scalar(
                            select(BankEntry).where(BankEntry.bank_account_id == account.id, BankEntry.reference_hash == hashed)
                        )
                        if previous:
                            if previous.amount != row["amount"] or previous.date != row["date"]:
                                raise BankError("BANK_ENTRY_CHANGED")
                            continue
                        entry = BankEntry(
                            **row,
                            household_id=cfg.household_id,
                            bank_account_id=account.id,
                            reference_hash=hashed,
                            reliable=reliable,
                            reviewed=False,
                            created_by=connection.user_id,
                        )
                        db.add(entry)
                        db.flush()
                        # Establish a baseline first: even today's history may already
                        # be included in an existing opening balance or manual records.
                        if not initial_sync:
                            register_expense(db, cfg, account, entry, member)
                        for subscription in (
                            []
                            if initial_sync
                            else db.scalars(
                                select(BankSubscription).where(
                                    BankSubscription.household_id == cfg.household_id, BankSubscription.user_id.in_(cfg.allowed_users)
                                )
                            )
                        ):
                            db.add(BankDelivery(household_id=cfg.household_id, subscription_id=subscription.id, entry_id=entry.id))
                    stage = "save_balances"
                    if balance is not None:
                        account.balance, account.balance_at = balance, now()
                    account.last_sync = now()
                stage = "commit"
                connection.last_sync, connection.error_code, connection.sync_diagnostic = now(), None, None
                audit(db, member, "bank.synced", connection.id)
            stage = "commit"
            db.commit()
            return True
        except Exception as exc:
            # Never persist/log provider bodies, account identifiers, credentials or exception strings.
            http_status = getattr(exc, "http_status", None)
            if http_status is None and stage in ("fetch_transactions", "parse_transactions", "fetch_balances", "parse_balances"):
                http_status = client.last_http_status
            diagnostic = failure_diagnostic(exc, stage, (time.monotonic() - started) * 1000, http_status)
            logging.getLogger(__name__).warning(
                "Bank synchronization failed: stage=%s type=%s code=%s http_status=%s",
                diagnostic["stage"],
                diagnostic["exception_type"],
                diagnostic["code"],
                diagnostic["http_status"],
            )
            # A failed flush/commit invalidates the SQLAlchemy transaction. Roll back
            # all imported records before persisting safe metadata in a fresh transaction.
            try:
                db.rollback()
                connection = db.scalar(
                    select(BankConnection)
                    .where(BankConnection.id == connection_id, BankConnection.household_id == cfg.household_id)
                    .with_for_update()
                )
                if connection and connection.status == "active" and connection.next_sync == lease_until:
                    connection.error_code, connection.sync_diagnostic = diagnostic["code"], diagnostic
                    if connection.error_code in ("EXPIRED_SESSION", "SESSION_EXPIRED", "REVOKED_SESSION", "CLOSED_SESSION"):
                        connection.status = "expired"
                    db.commit()
            except SQLAlchemyError:
                db.rollback()
                logging.getLogger(__name__).warning("Bank synchronization diagnostic could not be stored; database unavailable")
            return False


def deliver(cfg):
    with SessionLocal() as db:
        jobs = list(
            db.scalars(
                select(BankDelivery)
                .where(
                    BankDelivery.household_id == cfg.household_id,
                    BankDelivery.delivered_at.is_(None),
                    BankDelivery.attempts < 5,
                    BankDelivery.next_attempt <= now(),
                )
                .order_by(BankDelivery.created_at)
                .with_for_update(skip_locked=True)
                .limit(50)
            )
        )
        removed_subscriptions = set()
        for job in jobs:
            # A 410 deletes this subscription and cascades all its queued jobs.
            if job.subscription_id in removed_subscriptions:
                continue
            subscription = db.get(BankSubscription, job.subscription_id)
            entry = db.get(BankEntry, job.entry_id)
            member = db.scalar(select(Member.id).where(Member.household_id == cfg.household_id, Member.user_id == subscription.user_id))
            if not member or subscription.user_id not in cfg.allowed_users or not entry or entry.reviewed:
                job.delivered_at = now()
                continue
            job.attempts += 1
            try:
                payload = json.loads(cfg.open(subscription.payload_cipher))
                if not push_url_allowed(payload["endpoint"]):
                    raise ValueError()
                webpush(
                    subscription_info=payload,
                    data=json.dumps(
                        {
                            "title": "Nowy wpis do uzupełnienia",
                            "body": "Otwórz Razem, aby opisać operację lub dodać paragon.",
                            "url": "/bank",
                            "tag": "bank-" + entry.id,
                        }
                    ),
                    vapid_private_key=cfg.vapid_key_path,
                    vapid_claims={"sub": "mailto:" + cfg.contact_email},
                    ttl=3600,
                    timeout=10,
                )
                job.delivered_at = now()
            except WebPushException as exc:
                if exc.response is not None and exc.response.status_code in (404, 410):
                    db.execute(delete(BankSubscription).where(BankSubscription.id == subscription.id))
                    removed_subscriptions.add(subscription.id)
                    continue
                job.next_attempt = now() + timedelta(minutes=min(360, 2**job.attempts))
            except Exception:
                job.next_attempt = now() + timedelta(minutes=min(360, 2**job.attempts))
        db.commit()


def jobs():
    from .bank_provider import load_config

    cfg = load_config()
    if not cfg:
        return
    with SessionLocal() as db:
        ids = list(
            db.scalars(select(BankConnection.id).where(BankConnection.household_id == cfg.household_id, BankConnection.status == "active"))
        )
        revoked = list(
            db.scalars(
                select(BankConnection).where(BankConnection.household_id == cfg.household_id, BankConnection.status == "revoke_pending")
            )
        )
        for row in revoked:
            try:
                EnableBanking(cfg).revoke(cfg.open(row.session_cipher))
                row.session_cipher, row.status = None, "disconnected"
            except BankError as exc:
                if exc.code in ("HTTP_404", "SESSION_NOT_FOUND", "EXPIRED_SESSION"):
                    row.session_cipher, row.status = None, "disconnected"
        db.commit()
    for identifier in ids:
        sync_connection(cfg, identifier)
    deliver(cfg)


if __name__ == "__main__":
    try:
        jobs()
    except Exception:
        raise SystemExit("Bank worker failed; inspect connection status in the application.") from None
