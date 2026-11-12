"""Bank access is opt-in, bound to one configured household and two approved users."""

import json
import secrets
import tempfile
from pathlib import Path
from uuid import UUID
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import Field, StringConstraints
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from .bank_provider import (
    BankConfig,
    BankError,
    EnableBanking,
    config_path,
    decode_push_key,
    load_config,
    normalized_iban,
    push_url_allowed,
)
from .bank_diagnostics import public_diagnostic, safe_code
from .config import settings
from .bank_sync import matches, matches_account, sync_connection
from .db import get_db
from .domain import account_data, audit, create_transaction, creator_names, fingerprint, scoped, serialize, today
from .models import (
    Account,
    AccountAdjustment,
    Mutation,
    BankAccount,
    BankConnection,
    BankEntry,
    BankSubscription,
    Household,
    Member,
    Receipt,
    ReviewTask,
    Transaction,
    TransactionAllocation,
    User,
)
from .schemas import Schema, SignedMoney, SplitInput, TransactionInput
from .security import current_user, digest, hasher, household_member, rate_limit
from .settlements import ensure_open

router = APIRouter(tags=["private bank integration"])
Db = Annotated[Session, Depends(get_db)]
Membership = Annotated[Member, Depends(household_member)]
Key = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=100)]


def bank_access(user_id, household_id=None):
    cfg = load_config()
    if not cfg or (household_id is not None and cfg.household_id != household_id) or user_id not in cfg.allowed_users:
        raise HTTPException(404, "Integracja bankowa nie jest włączona dla tego domu.")
    return cfg


def guard(member, household_id, owner=False):
    cfg = bank_access(member.user_id, household_id)
    if owner and (member.user_id != cfg.owner_id or member.role != "owner"):
        raise HTTPException(403, "Połączeniem bankowym zarządza właściciel domu.")
    return cfg


def transaction_view(tx):
    return dict(
        id=tx.id,
        kind="refund" if tx.refund_of_id else tx.kind,
        amount=tx.amount,
        date=tx.date,
        description=tx.description,
        updated_at=tx.updated_at,
        refund_of_id=tx.refund_of_id,
    )


@router.get("/households/{household_id}/bank")
def bank_status(household_id: str, member: Membership, db: Db):
    try:
        cfg = guard(member, household_id)
    except HTTPException as exc:
        if exc.status_code == 404:
            user = db.get(User, member.user_id)
            if user and user.is_admin and member.role == "owner" and not config_path().exists():
                return {"enabled": False, "can_activate": True}
            return {"enabled": False}
        raise
    connections = list(
        db.scalars(
            select(BankConnection)
            .where(BankConnection.household_id == household_id)
            .order_by((BankConnection.status == "active").desc(), BankConnection.created_at.desc())
            .limit(20)
        )
    )
    balances = {row["id"]: row["balance"] for row in account_data(db, household_id)}
    accounts = list(db.scalars(select(BankAccount).where(BankAccount.household_id == household_id)))
    mapped_connections = {a.connection_id for a in accounts if a.account_id and a.start_date}
    current_time = datetime.now(timezone.utc)
    entries = list(
        db.scalars(
            select(BankEntry)
            .where(BankEntry.household_id == household_id)
            .order_by(BankEntry.reviewed.asc(), BankEntry.date.desc(), BankEntry.created_at.desc())
            .limit(501)
        )
    )
    from .refunds import refund_candidates

    by_id = {a.id: a for a in accounts}
    adjustments = list(
        db.scalars(
            select(AccountAdjustment)
            .where(AccountAdjustment.household_id == household_id)
            .order_by(AccountAdjustment.created_at.desc())
            .limit(50)
        )
    )
    authors = creator_names(db, adjustments)
    return dict(
        enabled=True,
        background_enabled=settings.app_env == "production",
        owner=member.user_id == cfg.owner_id and member.role == "owner",
        vapid_public_key=cfg.vapid_public_key,
        connections=[
            dict(
                id=c.id,
                status=c.status,
                valid_until=c.valid_until,
                last_sync=c.last_sync,
                next_sync=c.next_sync,
                error_code=safe_code(c.error_code) if c.error_code else None,
                sync_diagnostic=public_diagnostic(c.sync_diagnostic),
                sync_available=(
                    c.status == "active"
                    and c.id in mapped_connections
                    and (not c.next_sync or c.next_sync <= current_time)
                    and (not c.valid_until or c.valid_until > current_time)
                ),
            )
            for c in connections
        ],
        accounts=[
            dict(
                id=a.id,
                last4=a.last4,
                currency=a.currency,
                account_id=a.account_id,
                start_date=a.start_date,
                bank_balance=a.balance,
                balance_at=a.balance_at,
                app_balance=balances.get(a.account_id),
                difference=a.balance - balances[a.account_id] if a.balance is not None and a.account_id in balances else None,
                adjustments=[
                    dict(**serialize(r), created_by_name=authors.get(r.created_by)) for r in adjustments if r.account_id == a.account_id
                ][:10],
            )
            for a in accounts
        ],
        entries=[
            dict(
                id=e.id,
                bank_account_id=e.bank_account_id,
                amount=e.amount,
                date=e.date,
                description=e.description,
                reliable=e.reliable,
                match_method=e.match_method,
                reviewed=e.reviewed,
                updated_at=e.updated_at,
                transaction=transaction_view(db.get(Transaction, e.transaction_id)) if e.transaction_id else None,
                candidates=[transaction_view(tx) for tx in matches(db, e, by_id[e.bank_account_id])] if not e.transaction_id else [],
                refund_candidates=[
                    dict(**transaction_view(tx), remaining_amount=remaining)
                    for tx, remaining in refund_candidates(db, household_id, e.amount, e.date, exclude_refund_id=e.transaction_id)
                ]
                if e.amount > 0
                else [],
            )
            for e in entries[:500]
        ],
        truncated=len(entries) > 500,
        subscriptions=[
            dict(id=s.id, created_at=s.created_at)
            for s in db.scalars(
                select(BankSubscription).where(BankSubscription.household_id == household_id, BankSubscription.user_id == member.user_id)
            )
        ],
    )


@router.post("/households/{household_id}/bank/connect")
def bank_connect(household_id: str, member: Membership, db: Db):
    cfg = guard(member, household_id, owner=True)
    rate_limit("bank-connect:" + member.user_id, 3, 600)
    state = secrets.token_urlsafe(48)
    now = datetime.now(timezone.utc)
    client = EnableBanking(cfg)
    try:
        banks = [
            b for b in client.banks() if b.get("name") == "mBank" and b.get("country") == "PL" and "personal" in b.get("psu_types", [])
        ]
        if not banks:
            raise HTTPException(503, "mBank osobisty nie jest obecnie dostępny u dostawcy.")
        seconds = min(int(banks[0].get("maximum_consent_validity", 90 * 86400)), 90 * 86400)
        until = now + timedelta(seconds=seconds)
        result = client.authorize(state, until, "mBank")
        url = result["url"]
        if urlsplit(url).scheme != "https":
            raise ValueError()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(502, "Nie udało się rozpocząć połączenia z bankiem. Spróbuj ponownie.") from None
    row = BankConnection(
        household_id=household_id,
        user_id=member.user_id,
        created_by=member.user_id,
        status="pending",
        state_hash=digest(state),
        state_expires_at=now + timedelta(minutes=10),
        valid_until=until,
    )
    db.add(row)
    db.commit()
    return {"url": url}


class CompleteInput(Schema):
    code: str = Field(min_length=1, max_length=2048)
    state: str = Field(min_length=20, max_length=200)


class ActivationInput(Schema):
    app_id: UUID
    household_name: str = Field(min_length=1, max_length=80)
    password: Annotated[str, StringConstraints(strip_whitespace=False, min_length=10, max_length=128)]
    private_key: str = Field(min_length=100, max_length=16384)
    confirm_share: Literal[True]


@router.post("/households/{household_id}/bank/activate")
def bank_activate(household_id: str, data: ActivationInput, member: Membership, db: Db):
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
    from .bank_setup import eligible, write_config

    user = db.get(User, member.user_id)
    if not user or not user.is_admin or member.role != "owner":
        raise HTTPException(403, "Jednorazową aktywację wykonuje administrator będący właścicielem tego domu.")
    rate_limit("bank-activate:" + user.id, 3, 600)
    if not hasher.verify(data.password, user.password_hash):
        raise HTTPException(403, "Nieprawidłowe hasło konta.")
    if db.get(Household, household_id).name != data.household_name:
        raise HTTPException(422, "Wpisz dokładną nazwę wybranego domu.")
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('bank-activation', 0))"))
    if config_path().exists():
        raise HTTPException(409, "Bank jest już przypisany. Nie można zmienić domu ani nadpisać kluczy z panelu.")
    try:
        owner, users = eligible(db, household_id, user.email)
        raw = data.private_key.encode()
        key = load_pem_private_key(raw, password=None)
        if not isinstance(key, RSAPrivateKey) or key.key_size < 2048:
            raise ValueError()
        # Validate application identity without moving any bank/financial data.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "provider.pem"
            path.write_bytes(raw)
            path.chmod(0o600)
            cfg = BankConfig(household_id, user.id, users, str(data.app_id), str(path), "", "", "", user.email)
            result = EnableBanking(cfg).call("GET", "/application")
            if not result.get("active") or result.get("environment") != "PRODUCTION" or set(result.get("services", [])) != {"AIS"}:
                raise ValueError()
        write_config(household_id, str(data.app_id), owner, users, raw)
    except Exception:
        raise HTTPException(
            422,
            "Nie można aktywować integracji. Wymagane: dom z dwiema osobami, poprawny klucz RSA oraz aktywna aplikacja produkcyjna wyłącznie AIS.",
        ) from None
    audit(db, member, "bank.activated", household_id)
    db.commit()
    return {"ok": True}


@router.post("/bank/complete")
def bank_complete(data: CompleteInput, user: Annotated[User, Depends(current_user)], db: Db):
    cfg = bank_access(user.id)
    rate_limit("bank-complete:" + user.id, 10, 600)
    db.scalar(select(Household).where(Household.id == cfg.household_id).with_for_update())
    member = db.scalar(select(Member).where(Member.household_id == cfg.household_id, Member.user_id == user.id, Member.role == "owner"))
    row = db.scalar(
        select(BankConnection)
        .where(
            BankConnection.household_id == cfg.household_id,
            BankConnection.state_hash == digest(data.state),
            BankConnection.user_id == user.id,
        )
        .with_for_update()
    )
    if (
        not member
        or user.id != cfg.owner_id
        or not row
        or row.status != "pending"
        or not row.state_expires_at
        or row.state_expires_at <= datetime.now(timezone.utc)
    ):
        raise HTTPException(409, "Połączenie wygasło lub zostało już wykorzystane. Rozpocznij je ponownie.")
    # Consume the nonce before the external one-use code exchange, including on transport failure.
    row.state_hash, row.status = None, "exchanging"
    db.commit()
    session_id = None
    client = EnableBanking(cfg)
    try:
        result = client.session(data.code)
        session_id = result["session_id"]
        if (
            result.get("aspsp", {}).get("name") != "mBank"
            or result.get("aspsp", {}).get("country") != "PL"
            or result.get("psu_type") != "personal"
        ):
            raise ValueError()
        until = datetime.fromisoformat(result["access"]["valid_until"].replace("Z", "+00:00"))
        if until.tzinfo is None or until <= datetime.now(timezone.utc) or len(result["accounts"]) > 30:
            raise ValueError()
        db.scalar(select(Household).where(Household.id == cfg.household_id).with_for_update())
        row = db.scalar(select(BankConnection).where(BankConnection.id == row.id).with_for_update())
        if row:
            db.refresh(row, with_for_update=True)
        if not row or row.status != "exchanging":
            raise ValueError()
        guard(member, cfg.household_id, owner=True)
        if not db.scalar(
            select(Member.id).where(Member.household_id == cfg.household_id, Member.user_id == user.id, Member.role == "owner")
        ):
            raise ValueError()
        for item in result["accounts"]:
            if not item.get("uid"):
                continue
            if item["currency"] not in ("PLN", "EUR", "USD", "GBP", "CHF"):
                continue
            identity = digest(item["identification_hash"])
            account = db.scalar(
                select(BankAccount).where(BankAccount.household_id == cfg.household_id, BankAccount.identity_hash == identity)
            )
            iban = normalized_iban(item.get("account_id"))
            if not account:
                account = BankAccount(
                    household_id=cfg.household_id,
                    identity_hash=identity,
                    connection_id=row.id,
                    uid_cipher=cfg.seal(item["uid"]),
                    last4=iban[-4:] if iban else "",
                    iban_hash=digest(iban) if iban else None,
                    currency=item["currency"],
                    created_by=user.id,
                )
                db.add(account)
            elif account.currency != item["currency"]:
                raise ValueError()
            account.connection_id, account.uid_cipher = row.id, cfg.seal(item["uid"])
        for previous in db.scalars(
            select(BankConnection).where(
                BankConnection.household_id == cfg.household_id, BankConnection.id != row.id, BankConnection.status == "active"
            )
        ):
            previous.status = "revoke_pending"
        row.session_cipher, row.valid_until, row.status = cfg.seal(session_id), min(until, row.valid_until), "active"
        audit(db, member, "bank.connected", row.id)
        db.commit()
    except Exception:
        db.rollback()
        if session_id:
            try:
                client.revoke(session_id)
            except Exception:
                # Keep an encrypted revocation job if provider cleanup is temporarily unavailable.
                row = db.get(BankConnection, row.id)
                if row:
                    row.session_cipher, row.status = cfg.seal(session_id), "revoke_pending"
                    db.commit()
        raise HTTPException(502, "Nie udało się ukończyć połączenia. Rozpocznij ponownie; nie zaimportowano danych.") from None
    return {"household_id": cfg.household_id}


class MappingInput(Schema):
    account_id: str
    start_date: date


@router.put("/households/{household_id}/bank/accounts/{bank_account_id}")
def bank_map(household_id: str, bank_account_id: str, data: MappingInput, member: Membership, db: Db):
    guard(member, household_id, owner=True)
    db.scalar(select(Household).where(Household.id == household_id).with_for_update())
    bank = scoped(db, BankAccount, household_id, bank_account_id, lock=True)
    connection = db.get(BankConnection, bank.connection_id)
    if not connection or connection.status != "active":
        raise HTTPException(409, "Najpierw odnów połączenie z bankiem.")
    account = scoped(db, Account, household_id, data.account_id)
    if bank.account_id is not None:
        if bank.account_id == data.account_id and bank.start_date == data.start_date:
            return {"ok": True}
        raise HTTPException(
            409, "Rachunek jest już przypisany. Zmianę punktu początkowego wykonuje właściciel wdrożenia po uzgodnieniu historii."
        )
    if account.currency != bank.currency or account.currency != "PLN":
        raise HTTPException(422, "Na tym etapie księgowanie bankowe obsługuje rachunki PLN. Wybierz zgodne konto PLN.")
    if not today() - timedelta(days=90) <= data.start_date <= today():
        raise HTTPException(422, "Wybierz początek z ostatnich 90 dni, nie później niż dziś.")
    bank.account_id, bank.start_date = data.account_id, data.start_date
    if connection and connection.last_sync is None:
        connection.next_sync = None
    db.commit()
    return {"ok": True}


@router.post("/households/{household_id}/bank/sync")
def bank_refresh(household_id: str, member: Membership, db: Db):
    cfg = guard(member, household_id, owner=True)
    rate_limit("bank-refresh:" + member.user_id, 3, 60)
    connections = list(
        db.scalars(select(BankConnection).where(BankConnection.household_id == household_id, BankConnection.status == "active"))
    )
    synced, failed, waiting, unmapped = 0, 0, 0, 0
    next_sync = []
    for connection in connections:
        has_account = db.scalar(
            select(BankAccount.id)
            .where(
                BankAccount.household_id == household_id,
                BankAccount.connection_id == connection.id,
                BankAccount.account_id.is_not(None),
                BankAccount.start_date.is_not(None),
            )
            .limit(1)
        )
        if not has_account:
            unmapped += 1
            continue
        if connection.next_sync and connection.next_sync > datetime.now(timezone.utc):
            waiting += 1
        elif sync_connection(cfg, connection.id):
            synced += 1
        else:
            db.refresh(connection)
            if connection.error_code:
                failed += 1
            else:
                waiting += 1
        db.refresh(connection)
        if connection.next_sync:
            next_sync.append(connection.next_sync)
    if failed:
        message = "Próba synchronizacji nie powiodła się. Sprawdź szczegóły błędu i termin kolejnej próby. Poprzednie dane zachowano."
    elif synced:
        message = "Synchronizacja zakończona."
    elif waiting:
        message = "Nie rozpoczęto nowego pobierania. Kolejna próba będzie możliwa w podanym terminie — próby dzieli co najmniej 6 godzin."
    elif unmapped:
        message = "Najpierw przypisz rachunek do konta aplikacji i wybierz datę początku pobierania."
    else:
        message = "Brak aktywnej zgody bankowej. Połącz bank lub odnów zgodę."
    return {
        "synchronized": synced,
        "failed": failed,
        "waiting": waiting,
        "unmapped": unmapped,
        "next_sync": min(next_sync) if next_sync else None,
        "message": message,
    }


@router.delete("/households/{household_id}/bank/connections/{connection_id}")
def bank_disconnect(household_id: str, connection_id: str, member: Membership, db: Db):
    cfg = guard(member, household_id, owner=True)
    row = scoped(db, BankConnection, household_id, connection_id, lock=True)
    if row.session_cipher:
        row.status = "revoke_pending"
        db.commit()
        try:
            EnableBanking(cfg).revoke(cfg.open(row.session_cipher))
            row.session_cipher, row.status = None, "disconnected"
            db.commit()
        except BankError:
            return {"ok": True, "pending": True}
    else:
        row.status, row.state_hash = "disconnected", None
        db.commit()
    return {"ok": True, "pending": False}


class ResolveInput(Schema):
    action: Literal["new", "match", "transfer", "describe", "refund", "income"]
    expected_updated_at: datetime
    expected_transaction_updated_at: datetime | None = None
    transaction_id: str | None = None
    destination_id: str | None = None
    refund_of_id: str | None = None
    expected_original_updated_at: datetime | None = None
    description: str = Field(min_length=1, max_length=160)
    allocations: list[SplitInput] = Field(default_factory=list, max_length=150)


@router.post("/households/{household_id}/bank/entries/{entry_id}/resolve")
def bank_resolve(household_id: str, entry_id: str, data: ResolveInput, member: Membership, db: Db):
    guard(member, household_id)
    db.scalar(select(Household).where(Household.id == household_id).with_for_update())
    entry = scoped(db, BankEntry, household_id, entry_id, lock=True)
    if entry.updated_at != data.expected_updated_at:
        raise HTTPException(409, "Wpis bankowy został zmieniony. Odśwież listę.")
    account = scoped(db, BankAccount, household_id, entry.bank_account_id)
    tx = scoped(db, Transaction, household_id, entry.transaction_id, lock=True) if entry.transaction_id else None
    if tx and tx.updated_at != data.expected_transaction_updated_at:
        raise HTTPException(409, "Transakcja została zmieniona. Odśwież listę.")
    if tx and tx.refund_of_id and data.action not in ("describe", "income"):
        raise HTTPException(422, "Zapisany zwrot opisz lub zmień na zwykły wpływ przed inną klasyfikacją.")
    if data.action == "refund":
        from .refunds import RefundInput, create_refund

        if entry.amount <= 0 or not data.refund_of_id or not account.account_id or not data.expected_original_updated_at:
            raise HTTPException(422, "Wybierz zakup, którego dotyczy wpływ zwrotny.")
        original = scoped(db, Transaction, household_id, data.refund_of_id, lock=True)
        tx = create_refund(
            db,
            member,
            original,
            RefundInput(
                amount=entry.amount,
                date=entry.date,
                description=data.description,
                account_id=account.account_id,
                expected_updated_at=data.expected_original_updated_at,
            ),
            "refund-classify:" + entry.id + ":" + digest(data.expected_updated_at.isoformat())[:12],
            existing=tx,
            source="bank",
            source_id=entry.id,
        )
        entry.transaction_id, entry.reviewed = tx.id, True
    elif data.action == "income":
        if entry.amount <= 0 or not tx or not tx.refund_of_id:
            raise HTTPException(422, "Ta operacja nie jest zapisanym zwrotem.")
        ensure_open(db, household_id, tx.date.strftime("%Y-%m"))
        original = db.get(Transaction, tx.refund_of_id)
        tx.refund_of_id, tx.status, tx.description = None, "categorized", data.description
        tx.updated_at, tx.updated_by = datetime.now(timezone.utc), member.user_id
        if original:
            original.updated_at, original.updated_by = datetime.now(timezone.utc), member.user_id
        db.execute(delete(TransactionAllocation).where(TransactionAllocation.transaction_id == tx.id))
        entry.reviewed = True
    elif data.action == "describe" and tx and tx.refund_of_id:
        tx.description, tx.updated_by, tx.updated_at = data.description, member.user_id, datetime.now(timezone.utc)
        entry.reviewed = True
    elif data.action == "match":
        if tx or not data.transaction_id:
            raise HTTPException(409, "Ten wpis ma już transakcję lub nie wybrano dopasowania.")
        target = scoped(db, Transaction, household_id, data.transaction_id, lock=True)
        if target.id not in {candidate.id for candidate in matches(db, entry, account)}:
            raise HTTPException(422, "Wybrana transakcja nie pasuje do kwoty, rachunku lub daty.")
        entry.transaction_id, entry.reviewed = target.id, True
    else:
        ensure_open(db, household_id, entry.date.strftime("%Y-%m"))
        if not account.account_id:
            raise HTTPException(422, "Najpierw przypisz rachunek do konta aplikacji.")
        kind = "expense" if entry.amount < 0 else "income"
        source_id, destination_id = account.account_id, None
        if data.action == "transfer":
            if not data.destination_id or data.destination_id == account.account_id:
                raise HTTPException(422, "Wybierz drugie własne konto.")
            scoped(db, Account, household_id, data.destination_id)
            source_id, destination_id = (
                (account.account_id, data.destination_id) if entry.amount < 0 else (data.destination_id, account.account_id)
            )
            kind = "transfer"
        payload = TransactionInput(
            kind=kind,
            amount=abs(entry.amount),
            date=entry.date,
            description=data.description,
            account_id=source_id,
            destination_id=destination_id,
            allocations=data.allocations if kind == "expense" else [],
        )
        if tx and data.action == "describe":
            old_splits = [
                SplitInput(category_id=split.category_id, amount=split.amount)
                for split in db.scalars(select(TransactionAllocation).where(TransactionAllocation.transaction_id == tx.id))
            ]
            payload = TransactionInput(
                kind=tx.kind,
                amount=tx.amount,
                date=tx.date,
                description=data.description,
                account_id=tx.account_id,
                destination_id=tx.destination_id,
                member_id=tx.member_id,
                goal_id=tx.goal_id,
                allocations=data.allocations or old_splits,
            )
            kind = tx.kind
        if tx:
            if tx.source != "bank" or db.scalar(select(Receipt.id).where(Receipt.transaction_id == tx.id)):
                raise HTTPException(422, "Ten wpis ma już paragon lub pochodzi z ręcznego zapisu. Popraw go w odpowiednim ekranie.")
            from .domain import validate_transaction

            from .refunds import protect_refunded_purchase

            protect_refunded_purchase(db, tx, payload)
            validate_transaction(db, member, payload)
            for linked in db.scalars(select(BankEntry).where(BankEntry.household_id == household_id, BankEntry.transaction_id == tx.id)):
                linked_account = scoped(db, BankAccount, household_id, linked.bank_account_id)
                if not matches_account(payload, linked.amount, linked_account.account_id):
                    raise HTTPException(422, "Zmiana naruszyłaby dopasowanie drugiej operacji bankowej. Sprawdź obie strony przelewu.")
            db.execute(delete(TransactionAllocation).where(TransactionAllocation.transaction_id == tx.id))
            for key, value in payload.model_dump(exclude={"allocations"}).items():
                setattr(tx, key, value)
            for allocation in payload.allocations:
                db.add(
                    TransactionAllocation(
                        **allocation.model_dump(), transaction_id=tx.id, household_id=household_id, created_by=member.user_id
                    )
                )
            tx.status = "unallocated" if kind == "expense" and not payload.allocations else "categorized"
            tx.updated_by = member.user_id
        else:
            if data.action == "describe":
                raise HTTPException(422, "Wybierz nowy wpis, dopasowanie albo przelew własny.")
            tx = create_transaction(db, member, payload, "bank:" + entry.id, source="bank", source_id=entry.id)
            entry.transaction_id = tx.id
        entry.reviewed = True
        for task in db.scalars(select(ReviewTask).where(ReviewTask.transaction_id == tx.id, ReviewTask.household_id == household_id)):
            task.resolved = tx.status == "categorized"
    entry.match_method = "manual"
    entry.updated_by = member.user_id
    entry.updated_at = datetime.now(timezone.utc)
    if tx and tx.kind == "expense":
        db.flush()
        from .refunds import refund_allocations

        refund_allocations(db, tx, member.user_id)
    audit(db, member, "bank.reviewed", entry.id)
    db.commit()
    return {"ok": True}


@router.post("/households/{household_id}/bank/reconcile")
def bank_reconcile(household_id: str, member: Membership, db: Db):
    from .bank_matching import reconcile

    cfg = guard(member, household_id)
    result = reconcile(db, member, cfg)
    db.commit()
    return result


class BalanceAlignmentInput(Schema):
    expected_app_balance: SignedMoney
    expected_bank_balance: SignedMoney
    expected_bank_balance_at: datetime


@router.post("/households/{household_id}/bank/accounts/{bank_account_id}/align")
def bank_align(household_id: str, bank_account_id: str, data: BalanceAlignmentInput, key: Key, member: Membership, db: Db):
    guard(member, household_id, owner=True)
    db.scalar(select(Household).where(Household.id == household_id).with_for_update())
    signature = fingerprint("bank.align:" + bank_account_id, data.model_dump(mode="json"))
    previous = db.scalar(select(Mutation).where(Mutation.household_id == household_id, Mutation.key == key))
    if previous:
        if previous.request_hash != signature or previous.resource != "bank.align":
            raise HTTPException(409, "Ta korekta została już zapisana z innymi danymi.")
        return serialize(scoped(db, AccountAdjustment, household_id, previous.entity_id))
    bank = scoped(db, BankAccount, household_id, bank_account_id, lock=True)
    if not bank.account_id or bank.balance is None or not bank.balance_at:
        raise HTTPException(422, "Najpierw przypisz konto i pobierz saldo księgowe banku.")
    current = next(a["balance"] for a in account_data(db, household_id) if a["id"] == bank.account_id)
    if (
        current != data.expected_app_balance
        or bank.balance != data.expected_bank_balance
        or bank.balance_at != data.expected_bank_balance_at
    ):
        raise HTTPException(409, "Saldo aplikacji lub dane banku zmieniły się. Odśwież je przed wyrównaniem.")
    difference = bank.balance - current
    if not difference:
        return {"unchanged": True}
    row = AccountAdjustment(
        household_id=household_id,
        account_id=bank.account_id,
        amount=difference,
        balance_before=current,
        balance_after=bank.balance,
        bank_balance_at=bank.balance_at,
        created_by=member.user_id,
    )
    db.add(row)
    db.flush()
    db.add(
        Mutation(
            household_id=household_id, key=key, resource="bank.align", entity_id=row.id, request_hash=signature, created_by=member.user_id
        )
    )
    audit(db, member, "bank.balance_aligned", row.id)
    db.commit()
    return serialize(row)


class SubscriptionInput(Schema):
    endpoint: str = Field(max_length=2048)
    keys: dict[str, str] = Field(max_length=2)


@router.post("/households/{household_id}/bank/subscriptions")
def subscribe(household_id: str, data: SubscriptionInput, member: Membership, db: Db):
    cfg = guard(member, household_id)
    if (
        not push_url_allowed(data.endpoint)
        or set(data.keys) != {"auth", "p256dh"}
        or not decode_push_key(data.keys["auth"], 16)
        or not decode_push_key(data.keys["p256dh"], 65)
    ):
        raise HTTPException(422, "Nieobsługiwane lub nieprawidłowe powiadomienia tej przeglądarki.")
    db.scalar(select(Member).where(Member.id == member.id).with_for_update())
    hashed = digest(data.endpoint)
    row = db.scalar(select(BankSubscription).where(BankSubscription.user_id == member.user_id, BankSubscription.endpoint_hash == hashed))
    if not row:
        if db.scalar(select(func.count()).select_from(BankSubscription).where(BankSubscription.user_id == member.user_id)) >= 10:
            raise HTTPException(409, "Odłącz nieużywane urządzenie (limit 10).")
        row = BankSubscription(household_id=household_id, user_id=member.user_id, endpoint_hash=hashed, created_by=member.user_id)
        db.add(row)
    row.payload_cipher = cfg.seal(json.dumps(data.model_dump()))
    db.commit()
    return {"id": row.id}


@router.delete("/households/{household_id}/bank/subscriptions/{subscription_id}")
def unsubscribe(household_id: str, subscription_id: str, member: Membership, db: Db):
    guard(member, household_id)
    row = db.scalar(
        select(BankSubscription).where(
            BankSubscription.id == subscription_id,
            BankSubscription.household_id == household_id,
            BankSubscription.user_id == member.user_id,
        )
    )
    if not row:
        raise HTTPException(404, "Nie znaleziono urządzenia.")
    db.delete(row)
    db.commit()
    return {"ok": True}


def receipt_candidates(db, household_id, amount, account_id, receipt_date):
    return list(
        db.scalars(
            select(Transaction)
            .where(
                Transaction.household_id == household_id,
                Transaction.kind == "expense",
                Transaction.account_id == account_id,
                Transaction.amount == amount,
                Transaction.date >= receipt_date - timedelta(days=7),
                Transaction.date <= receipt_date + timedelta(days=7),
                Transaction.id.in_(select(BankEntry.transaction_id).where(BankEntry.household_id == household_id)),
                ~Transaction.id.in_(
                    select(Receipt.transaction_id).where(Receipt.transaction_id.is_not(None), Receipt.household_id == household_id)
                ),
            )
            .order_by(Transaction.date.desc())
            .limit(30)
        )
    )


@router.get("/households/{household_id}/bank/receipt-matches")
def receipt_matches(household_id: str, member: Membership, db: Db, amount: int, account_id: str, receipt_date: date):
    guard(member, household_id)
    scoped(db, Account, household_id, account_id)
    return [transaction_view(tx) for tx in receipt_candidates(db, household_id, amount, account_id, receipt_date)]
