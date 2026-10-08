import hashlib
import logging
import secrets
from collections import defaultdict
from datetime import date as DateValue, datetime, timedelta, timezone
from typing import Annotated, Literal

from fastapi import Query, Depends, FastAPI, File, Header, HTTPException, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import and_, delete, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .domain import (
    account_data,
    pln_account,
    audit,
    budget_data,
    classify,
    create_transaction,
    create_record,
    fingerprint,
    goal_data,
    learn,
    month_dates,
    month_valid,
    records,
    recurring_data,
    scoped,
    serialize,
    today,
    transaction_data,
    validate_transaction,
)
from .exchange import value_accounts
from .middleware import RequestBodyLimit
from .models import (
    Account,
    Audit,
    BudgetAllocation,
    Category,
    ClassificationRule,
    Goal,
    Household,
    Invitation,
    IncomeSource,
    Member,
    Mutation,
    Period,
    Receipt,
    ReceiptItem,
    Recurring,
    ReviewTask,
    SessionToken,
    Transaction,
    TransactionAllocation,
    User,
)
from .schedules import occurrence_dates, calendar_text, reminders
from .receipts import MAX_IMAGE_BYTES, provider, storage_path, validated_image
from .schemas import (
    AccountInput,
    BudgetInput,
    CategoryInput,
    Credentials,
    FinalizeInput,
    GoalInput,
    HouseholdInput,
    JoinInput,
    DraftReceiptInput,
    RecurringInput,
    SplitInput,
    TransactionInput,
    TransactionEditInput,
)
from .security import DUMMY_HASH, current_user, digest, hasher, household_member, rate_limit, set_session

logger = logging.getLogger(__name__)

app = FastAPI(title="Dom · budżet domowy", version="1.0.0")
app.add_middleware(RequestBodyLimit)
Db = Annotated[Session, Depends(get_db)]
Person = Annotated[User, Depends(current_user)]
Membership = Annotated[Member, Depends(household_member)]
Key = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=100)]


@app.middleware("http")
async def security_headers(request: Request, call_next):
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") != settings.web_origin.rstrip("/"):
            return JSONResponse({"detail": "Niedozwolone źródło żądania."}, status_code=403)
        # SameSite=Strict protects forms; origin checked whenever browsers send it.
        if request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"detail": "Niedozwolone żądanie."}, status_code=403)
        size = request.headers.get("content-length")
        if size and (not size.isdigit() or int(size) > MAX_IMAGE_BYTES + 65536):
            return JSONResponse({"detail": "Plik jest za duży (maks. 10 MB)."}, status_code=413)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    # Do not echo request input, which may contain passwords.
    return JSONResponse({"detail": "Sprawdź dane formularza. Uzupełnij wymagane pola i popraw nieprawidłowe wartości."}, status_code=422)


@app.exception_handler(IntegrityError)
async def integrity_error(request, exc):
    return JSONResponse({"detail": "Nie można zapisać danych. Nazwa lub operacja już istnieje albo dane są niespójne."}, status_code=409)


@app.get("/health")
def health(db: Db):
    from sqlalchemy import text

    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.post("/auth/register", status_code=201)
def register(data: Credentials, request: Request, response: Response, db: Db):
    rate_limit(f"auth:{request.client.host}", 15)
    if db.scalar(select(User.id).where(User.email == data.email)):
        raise HTTPException(409, "Ten adres e-mail jest już używany.")
    user = User(name=data.name, email=data.email, password_hash=hasher.hash(data.password))
    db.add(user)
    db.flush()
    set_session(db, user, response)
    db.commit()
    return serialize(user)


@app.post("/auth/login")
def login(data: Credentials, request: Request, response: Response, db: Db):
    rate_limit(f"login:{data.email}", 15)
    rate_limit(f"login-ip:{request.client.host}", 120)
    user = db.scalar(select(User).where(User.email == data.email))
    correct = hasher.verify(data.password, user.password_hash if user else DUMMY_HASH)
    if not user or not correct:
        raise HTTPException(401, "Nieprawidłowy e-mail lub hasło.")
    set_session(db, user, response)
    db.commit()
    return serialize(user)


@app.post("/auth/logout")
def logout(request: Request, response: Response, db: Db):
    raw = request.cookies.get("dom_session")
    if raw:
        db.execute(delete(SessionToken).where(SessionToken.token_hash == digest(raw)))
        db.commit()
    response.delete_cookie("dom_session", path="/")
    return {"ok": True}


@app.get("/auth/me")
def me(user: Person, db: Db):
    households = [
        dict(**serialize(db.get(Household, m.household_id)), member_id=m.id, role=m.role)
        for m in db.scalars(select(Member).where(Member.user_id == user.id))
    ]
    return {
        "user": serialize(user),
        "households": households,
        "receipt_provider": settings.receipt_provider,
        "receipt_ai_available": settings.receipt_ai_available,
        "thresholds": {
            "auto": round(settings.classification_auto_threshold * 100),
            "review": round(settings.classification_review_threshold * 100),
        },
    }


@app.post("/households", status_code=201)
def household_create(data: HouseholdInput, key: Key, user: Person, db: Db):
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    signature = fingerprint("households", data.model_dump())
    previous = db.scalar(select(Mutation).where(Mutation.created_by == user.id, Mutation.resource == "households", Mutation.key == key))
    if previous:
        if previous.request_hash != signature:
            raise HTTPException(409, "Ten zapis już istnieje z innymi danymi.")
        return serialize(db.get(Household, previous.entity_id))
    household = Household(name=data.name, created_by=user.id)
    db.add(household)
    db.flush()
    db.add(Member(household_id=household.id, user_id=user.id, role="owner", created_by=user.id))
    db.add(
        Mutation(
            household_id=household.id, key=key, resource="households", request_hash=signature, entity_id=household.id, created_by=user.id
        )
    )
    db.add(Account(household_id=household.id, name="Konto wspólne", created_by=user.id))
    db.add(Account(household_id=household.id, name="Oszczędności", kind="savings", created_by=user.id))
    defaults = [
        ("Mieszkanie", "Potrzeby", "house", "green"),
        ("Jedzenie", "Potrzeby", "basket", "green"),
        ("Rachunki", "Potrzeby", "zap", "amber"),
        ("Transport", "Potrzeby", "car", "blue"),
        ("Przyjemności", "Na co dzień", "coffee", "purple"),
        ("Dom i zakupy", "Na co dzień", "shopping", "blue"),
    ]
    for name, group, icon, color in defaults:
        db.add(Category(household_id=household.id, name=name, group=group, icon=icon, color=color, created_by=user.id))
    db.commit()
    return serialize(household)


@app.post("/households/join")
def join(data: JoinInput, user: Person, db: Db):
    invitation = db.scalar(select(Invitation).where(Invitation.token_hash == digest(data.token)).with_for_update())
    if not invitation or invitation.expires_at <= datetime.now(timezone.utc) or invitation.used_by:
        raise HTTPException(422, "Zaproszenie wygasło lub zostało już użyte.")
    if db.scalar(select(Member.id).where(Member.household_id == invitation.household_id, Member.user_id == user.id)):
        raise HTTPException(409, "Jesteś już w tym gospodarstwie.")
    db.add(Member(household_id=invitation.household_id, user_id=user.id, created_by=user.id))
    invitation.used_by = user.id
    db.commit()
    return serialize(db.get(Household, invitation.household_id))


@app.post("/households/{household_id}/invitations")
def invite(household_id: str, member: Membership, db: Db):
    if member.role != "owner":
        raise HTTPException(403, "Zaproszenia tworzy właściciel gospodarstwa.")
    raw = secrets.token_urlsafe(32)
    db.add(
        Invitation(
            household_id=household_id,
            token_hash=digest(raw),
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            created_by=member.user_id,
        )
    )
    db.commit()
    return {"token": raw, "expires_in_days": 7}


@app.get("/households/{household_id}/overview")
def overview(household_id: str, month: str, member: Membership, db: Db):
    month_valid(month)
    members = [dict(**serialize(m), name=db.get(User, m.user_id).name) for m in records(db, Member, household_id)]
    tasks = [serialize(t) for t in records(db, ReviewTask, household_id) if not t.resolved]
    start, end = month_dates(month)
    transactions = list(
        db.scalars(
            select(Transaction)
            .where(Transaction.household_id == household_id, Transaction.date >= start, Transaction.date <= end)
            .order_by(Transaction.date.desc(), Transaction.created_at.desc())
            .limit(6)
        )
    )
    accounts = account_data(db, household_id)
    valuation = value_accounts(accounts)
    return dict(
        account_valuation=valuation,
        household=serialize(db.get(Household, household_id)),
        members=members,
        categories=[serialize(c) for c in records(db, Category, household_id)],
        budget=budget_data(db, household_id, month),
        accounts=accounts,
        goals=goal_data(db, household_id),
        tasks=tasks,
        recent=[transaction_data(db, t) for t in transactions],
        recurring=recurring_data(db, household_id, month),
        reminders=reminders(db, household_id, today()),
        rules=[serialize(r) for r in records(db, ClassificationRule, household_id)],
    )


@app.get("/households/{household_id}/budget/{month}")
def budget_read(household_id: str, month: str, member: Membership, db: Db):
    return budget_data(db, household_id, month)


@app.put("/households/{household_id}/budget/{month}")
def budget_save(
    household_id: str,
    month: str,
    data: BudgetInput,
    member: Membership,
    db: Db,
    key: Annotated[str | None, Header(alias="Idempotency-Key", min_length=8, max_length=100)] = None,
):
    month_valid(month)
    db.scalar(select(Household).where(Household.id == household_id).with_for_update())
    if len({(a.kind, a.reference_id) for a in data.allocations}) != len(data.allocations):
        raise HTTPException(422, "Powtórzona pozycja budżetu.")
    signature = fingerprint("budget.save:" + month, data.model_dump(mode="json"))
    if key:
        previous = db.scalar(select(Mutation).where(Mutation.household_id == household_id, Mutation.key == key))
        if previous:
            if previous.request_hash != signature:
                raise HTTPException(409, "Ten zapis już istnieje z innymi danymi. Odśwież formularz.")
            return budget_data(db, household_id, month)
    period = db.scalar(select(Period).where(Period.household_id == household_id, Period.month == month))
    if "expected_updated_at" in data.model_fields_set and data.expected_updated_at != (period.updated_at if period else None):
        raise HTTPException(409, "Ten plan został zmieniony. Odśwież stronę przed ponownym zapisem.")
    if not period:
        period = Period(household_id=household_id, month=month, created_by=member.user_id)
        db.add(period)
        db.flush()
    old = {(a.kind, a.reference_id): a for a in db.scalars(select(BudgetAllocation).where(BudgetAllocation.period_id == period.id))}
    # PUT replaces the monthly source list atomically; retries cannot append it twice.
    sources = data.income_sources
    if sources is not None:
        pairs = [(" ".join(source.name.casefold().split()), source.member_id) for source in sources]
        if len(set(pairs)) != len(pairs):
            raise HTTPException(422, "Ta osoba ma już źródło o tej nazwie. Połącz kwoty lub zmień nazwę.")
        for source in sources:
            if source.member_id is not None:
                scoped(db, Member, household_id, source.member_id)
    if sources is not None or period.planned_income != data.planned_income:
        db.execute(delete(IncomeSource).where(IncomeSource.period_id == period.id, IncomeSource.household_id == household_id))
        if sources is not None:
            for position, source in enumerate(sources):
                db.add(
                    IncomeSource(
                        household_id=household_id,
                        period_id=period.id,
                        position=position,
                        **source.model_dump(),
                        created_by=member.user_id,
                        updated_by=member.user_id,
                    )
                )
            period.planned_income = sum(source.amount for source in sources)
        else:
            period.planned_income = data.planned_income
            if data.planned_income:
                db.add(
                    IncomeSource(
                        household_id=household_id,
                        period_id=period.id,
                        position=0,
                        name="Dochód wspólny",
                        amount=data.planned_income,
                        created_by=member.user_id,
                    )
                )
    period.updated_by = member.user_id
    period.updated_at = datetime.now(timezone.utc)
    keep = set()
    for entry in data.allocations:
        if entry.kind == "category":
            category = scoped(db, Category, household_id, entry.reference_id)
            label, group = category.name, category.group
            if category.archived and entry.amount and (entry.kind, entry.reference_id) not in old:
                raise HTTPException(422, "Nie możesz planować zarchiwizowanej kategorii.")
        elif entry.kind == "pocket":
            recipient = scoped(db, Member, household_id, entry.reference_id)
            label, group = db.get(User, recipient.user_id).name, "Kieszonkowe"
        else:
            goal = scoped(db, Goal, household_id, entry.reference_id)
            label, group = goal.name, "Przyszłość"
        pair = (entry.kind, entry.reference_id)
        keep.add(pair)
        if pair in old:
            old[pair].amount = entry.amount
            old[pair].updated_by = member.user_id
        else:
            db.add(
                BudgetAllocation(
                    household_id=household_id,
                    period_id=period.id,
                    kind=entry.kind,
                    reference_id=entry.reference_id,
                    amount=entry.amount,
                    label=label,
                    group=group,
                    created_by=member.user_id,
                )
            )
    for pair, allocation in old.items():
        if pair not in keep:
            db.delete(allocation)
    if key:
        db.add(
            Mutation(
                household_id=household_id,
                key=key,
                resource="budget.save",
                request_hash=signature,
                entity_id=period.id,
                created_by=member.user_id,
            )
        )
    audit(db, member, "budget.saved", period.id)
    db.commit()
    return budget_data(db, household_id, month)


@app.get("/households/{household_id}/budget/{month}/copy-preview")
def budget_copy_preview(household_id: str, month: str, source_month: str, member: Membership, db: Db):
    month_valid(month)
    month_valid(source_month)
    if source_month == month:
        raise HTTPException(422, "Wybierz inny miesiąc do skopiowania.")
    source = budget_data(db, household_id, source_month)
    if not source["period"]:
        raise HTTPException(404, "W tym miesiącu nie ma jeszcze planu.")
    active = {("category", c.id) for c in records(db, Category, household_id) if not c.archived}
    active |= {("pocket", m.id) for m in records(db, Member, household_id)}
    active |= {("goal", g.id) for g in records(db, Goal, household_id)}
    allocations, omitted = [], []
    for row in source["allocations"]:
        if row["id"].startswith("actual-"):
            continue
        if (row["kind"], row["reference_id"]) not in active:
            omitted.append(row["label"])
        else:
            allocations.append({k: row[k] for k in ("kind", "reference_id", "amount", "label")})
    return dict(
        source_month=source_month,
        planned_income=source["planned_income"],
        income_sources=[{k: row[k] for k in ("name", "member_id", "amount")} for row in source["income_sources"]],
        allocations=allocations,
        omitted=omitted,
    )


@app.post("/households/{household_id}/categories", status_code=201)
def category_create(household_id: str, data: CategoryInput, key: Key, member: Membership, db: Db):
    category = create_record(db, member, Category, data.model_dump(), key)
    db.add(category)
    db.commit()
    return serialize(category)


@app.patch("/households/{household_id}/categories/{category_id}")
def category_update(household_id: str, category_id: str, data: CategoryInput, member: Membership, db: Db):
    category = scoped(db, Category, household_id, category_id)
    for key, value in data.model_dump().items():
        setattr(category, key, value)
    category.updated_by = member.user_id
    db.commit()
    return serialize(category)


@app.delete("/households/{household_id}/categories/{category_id}")
def category_archive(household_id: str, category_id: str, member: Membership, db: Db):
    category = scoped(db, Category, household_id, category_id)
    if db.scalar(
        select(Recurring.id).where(Recurring.household_id == household_id, Recurring.category_id == category_id, Recurring.active.is_(True))
    ):
        raise HTTPException(409, "Najpierw zmień kategorię lub wyłącz stały wydatek, który jej używa.")
    category.archived = True
    category.updated_by = member.user_id
    db.commit()
    return {"ok": True}


@app.post("/households/{household_id}/transactions", status_code=201)
def transaction_create(household_id: str, data: TransactionInput, key: Key, member: Membership, db: Db):
    tx = create_transaction(db, member, data, key)
    db.commit()
    return transaction_data(db, tx)


@app.get("/households/{household_id}/transactions")
def transaction_list(
    household_id: str,
    member: Membership,
    db: Db,
    month: str | None = None,
    kind: Literal["expense", "income", "pocket", "transfer", "saving"] | None = None,
    search: str = "",
    offset: int = 0,
    limit: int = 30,
    category_id: str | None = None,
    account_id: str | None = None,
    date_from: DateValue | None = None,
    date_to: DateValue | None = None,
    min_amount: Annotated[int | None, Query(ge=0, le=100_000_000_000)] = None,
    max_amount: Annotated[int | None, Query(ge=0, le=100_000_000_000)] = None,
    sort: Literal["newest", "oldest", "amount_desc", "amount_asc"] = "newest",
):
    if offset < 0 or not 1 <= limit <= 100 or len(search) > 160:
        raise HTTPException(422, "Nieprawidłowe filtry.")
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "Data od nie może być późniejsza niż data do.")
    if any(d and not 2000 <= d.year <= 2100 for d in (date_from, date_to)):
        raise HTTPException(422, "Wybierz daty pomiędzy 2000 a 2100 rokiem.")
    if min_amount is not None and max_amount is not None and min_amount > max_amount:
        raise HTTPException(422, "Kwota od nie może przekraczać kwoty do.")
    query = select(Transaction).where(Transaction.household_id == household_id)
    if month:
        start, end = month_dates(month)
        query = query.where(Transaction.date >= start, Transaction.date <= end)
    if date_from:
        query = query.where(Transaction.date >= date_from)
    if date_to:
        query = query.where(Transaction.date <= date_to)
    if kind:
        query = query.where(Transaction.kind == kind)
    if account_id:
        scoped(db, Account, household_id, account_id)
        query = query.where(or_(Transaction.account_id == account_id, Transaction.destination_id == account_id))
    if category_id:
        scoped(db, Category, household_id, category_id)
        matching = (
            select(TransactionAllocation.id)
            .where(
                TransactionAllocation.household_id == household_id,
                TransactionAllocation.transaction_id == Transaction.id,
                TransactionAllocation.category_id == category_id,
            )
            .exists()
        )
        query = query.where(matching)
    if min_amount is not None:
        query = query.where(Transaction.amount >= min_amount)
    if max_amount is not None:
        query = query.where(Transaction.amount <= max_amount)
    if search.strip():
        pattern = "%" + search.strip().replace("%", "\\%").replace("_", "\\_") + "%"
        receipt_match = (
            select(ReceiptItem.id)
            .join(Receipt, Receipt.id == ReceiptItem.receipt_id)
            .where(
                Receipt.household_id == household_id,
                ReceiptItem.household_id == household_id,
                Receipt.transaction_id == Transaction.id,
                ReceiptItem.name.ilike(pattern, escape="\\"),
            )
            .exists()
        )
        query = query.where(or_(Transaction.description.ilike(pattern, escape="\\"), receipt_match))
    ordering = {
        "newest": Transaction.date.desc(),
        "oldest": Transaction.date.asc(),
        "amount_desc": Transaction.amount.desc(),
        "amount_asc": Transaction.amount.asc(),
    }[sort]
    txs = list(db.scalars(query.order_by(ordering, Transaction.created_at.desc(), Transaction.id).offset(offset).limit(limit + 1)))
    return {"items": [transaction_data(db, t) for t in txs[:limit]], "has_more": len(txs) > limit}


@app.get("/households/{household_id}/transactions/{transaction_id}")
def transaction_get(household_id: str, transaction_id: str, member: Membership, db: Db):
    return transaction_data(db, scoped(db, Transaction, household_id, transaction_id))


@app.put("/households/{household_id}/transactions/{transaction_id}")
def transaction_edit(household_id: str, transaction_id: str, data: TransactionEditInput, key: Key, member: Membership, db: Db):
    db.scalar(select(Household).where(Household.id == household_id).with_for_update())
    tx = scoped(db, Transaction, household_id, transaction_id, lock=True)
    signature = fingerprint("transaction.edit:" + transaction_id, data.model_dump(mode="json"))
    previous = db.scalar(select(Mutation).where(Mutation.household_id == household_id, Mutation.key == key))
    if previous:
        if previous.request_hash != signature:
            raise HTTPException(409, "Ten zapis już istnieje z innymi danymi. Odśwież formularz.")
        return transaction_data(db, tx)
    if data.expected_updated_at != tx.updated_at:
        raise HTTPException(409, "Ta transakcja została zmieniona. Odśwież ją przed ponowną edycją.")
    if data.kind != tx.kind:
        raise HTTPException(422, "Nie można zmienić rodzaju zapisanej transakcji.")
    movement = TransactionInput.model_validate(data.model_dump(exclude={"expected_updated_at"}))
    old_allocations = list(db.scalars(select(TransactionAllocation).where(TransactionAllocation.transaction_id == tx.id)))
    if tx.source == "receipt":
        old_splits = sorted((a.category_id, a.amount) for a in old_allocations)
        new_splits = sorted((a.category_id, a.amount) for a in movement.allocations)
        if movement.amount != tx.amount or movement.date != tx.date or old_splits != new_splits:
            raise HTTPException(422, "Kwota, data i pozycje pochodzą z zatwierdzonego paragonu. Możesz zmienić opis lub konto.")
    validate_transaction(db, member, movement, existing=old_allocations)
    for name, value in movement.model_dump(exclude={"allocations"}).items():
        setattr(tx, name, value)
    db.execute(delete(TransactionAllocation).where(TransactionAllocation.transaction_id == tx.id))
    for entry in movement.allocations:
        db.add(
            TransactionAllocation(
                **entry.model_dump(), transaction_id=tx.id, household_id=household_id, created_by=member.user_id, updated_by=member.user_id
            )
        )
    tx.status = "unallocated" if tx.kind == "expense" and not movement.allocations else "categorized"
    tx.updated_by = member.user_id
    tx.updated_at = datetime.now(timezone.utc)
    tasks = list(db.scalars(select(ReviewTask).where(ReviewTask.household_id == household_id, ReviewTask.transaction_id == tx.id)))
    for task in tasks:
        task.resolved = True
        task.updated_by = member.user_id
    if tx.status == "unallocated":
        db.add(
            ReviewTask(household_id=household_id, transaction_id=tx.id, kind="unallocated", title=tx.description, created_by=member.user_id)
        )
    db.add(
        Mutation(
            household_id=household_id,
            key=key,
            resource="transaction.edit",
            request_hash=signature,
            entity_id=tx.id,
            created_by=member.user_id,
        )
    )
    audit(db, member, "transaction.updated", tx.id)
    db.commit()
    return transaction_data(db, tx)


@app.put("/households/{household_id}/transactions/{transaction_id}/allocations")
def transaction_categorize(household_id: str, transaction_id: str, data: list[SplitInput], member: Membership, db: Db):
    tx = scoped(db, Transaction, household_id, transaction_id, lock=True)
    if tx.kind != "expense" or sum(a.amount for a in data) != tx.amount or len({a.category_id for a in data}) != len(data):
        raise HTTPException(422, "Suma kategorii musi być równa kwocie wydatku.")
    for entry in data:
        if scoped(db, Category, household_id, entry.category_id).archived:
            raise HTTPException(422, "Wybierz aktywną kategorię.")
    db.execute(
        delete(TransactionAllocation).where(
            TransactionAllocation.transaction_id == tx.id, TransactionAllocation.household_id == household_id
        )
    )
    for entry in data:
        db.add(TransactionAllocation(**entry.model_dump(), transaction_id=tx.id, household_id=household_id, created_by=member.user_id))
    tx.status = "categorized"
    tx.updated_by = member.user_id
    for task in db.scalars(select(ReviewTask).where(ReviewTask.household_id == household_id, ReviewTask.transaction_id == tx.id)):
        task.resolved = True
        task.updated_by = member.user_id
    audit(db, member, "transaction.categorized", tx.id)
    db.commit()
    return transaction_data(db, tx)


@app.post("/households/{household_id}/goals", status_code=201)
def goal_create(household_id: str, data: GoalInput, key: Key, member: Membership, db: Db):
    goal = create_record(db, member, Goal, data.model_dump(), key)
    db.add(goal)
    db.commit()
    return serialize(goal)


@app.put("/households/{household_id}/goals/{goal_id}")
def goal_update(household_id: str, goal_id: str, data: GoalInput, member: Membership, db: Db):
    goal = scoped(db, Goal, household_id, goal_id)
    for key, value in data.model_dump().items():
        setattr(goal, key, value)
    goal.updated_by = member.user_id
    audit(db, member, "goal.updated", goal.id)
    db.commit()
    return serialize(goal)


@app.post("/households/{household_id}/accounts", status_code=201)
def account_create(household_id: str, data: AccountInput, key: Key, member: Membership, db: Db):
    account = create_record(db, member, Account, data.model_dump(), key)
    db.add(account)
    db.commit()
    return serialize(account)


@app.post("/households/{household_id}/recurring", status_code=201)
def recurring_create(household_id: str, data: RecurringInput, key: Key, member: Membership, db: Db):
    category = scoped(db, Category, household_id, data.category_id)
    if category.archived:
        raise HTTPException(422, "Wybierz aktywną kategorię.")
    pln_account(db, household_id, data.account_id)
    row = create_record(db, member, Recurring, data.model_dump(), key)
    db.add(row)
    db.commit()
    return serialize(row)


@app.put("/households/{household_id}/recurring/{recurring_id}")
def recurring_update(household_id: str, recurring_id: str, data: RecurringInput, member: Membership, db: Db):
    row = scoped(db, Recurring, household_id, recurring_id)
    category = scoped(db, Category, household_id, data.category_id)
    if category.archived and data.active:
        raise HTTPException(422, "Wybierz aktywną kategorię dla stałego wydatku.")
    pln_account(db, household_id, data.account_id)
    for key, value in data.model_dump().items():
        setattr(row, key, value)
    row.updated_by = member.user_id
    db.commit()
    return serialize(row)


@app.post("/households/{household_id}/recurring/{recurring_id}/pay/{occurrence}")
def recurring_pay(household_id: str, recurring_id: str, occurrence: str, member: Membership, db: Db):
    row = scoped(db, Recurring, household_id, recurring_id)
    if not row.active:
        raise HTTPException(422, "Ten cykliczny wydatek jest wyłączony.")
    if len(occurrence) == 7:
        start, end = month_dates(occurrence)
        dates = occurrence_dates(row, start, end)
        if len(dates) != 1:
            raise HTTPException(422, "Wybierz konkretną płatność z tego miesiąca.")
        due = dates[0]
    else:
        try:
            due = datetime.strptime(occurrence, "%Y-%m-%d").date()
        except ValueError as error:
            raise HTTPException(422, "Nieprawidłowa data płatności.") from error
        month_valid(due.strftime("%Y-%m"))
        if occurrence_dates(row, due, due) != [due]:
            raise HTTPException(422, "Ta data nie należy do harmonogramu płatności.")
        start, end = month_dates(due.strftime("%Y-%m"))
    key = f"recurring:{row.id}:{due.isoformat()}"
    keys = [key]
    if row.frequency == "monthly":
        keys.append(f"recurring:{row.id}:{due:%Y-%m}")
    db.scalar(select(Household).where(Household.id == household_id).with_for_update())
    existing = db.scalar(
        select(Transaction).where(
            Transaction.household_id == household_id,
            Transaction.source == "recurring",
            Transaction.source_id == row.id,
            or_(Transaction.idempotency_key.in_(keys), Transaction.date == due),
        )
    )
    if existing:
        return transaction_data(db, existing)
    data = TransactionInput(
        kind="expense",
        amount=row.amount,
        date=due,
        description=row.name,
        account_id=row.account_id,
        allocations=[SplitInput(category_id=row.category_id, amount=row.amount)],
    )
    tx = create_transaction(db, member, data, key, source="recurring", source_id=row.id)
    db.commit()
    return transaction_data(db, tx)


@app.get("/households/{household_id}/reminders")
def reminder_list(household_id: str, member: Membership, db: Db):
    return reminders(db, household_id, today())


@app.get("/households/{household_id}/recurring/calendar")
def recurring_calendar(household_id: str, member: Membership, db: Db):
    content = calendar_text(records(db, Recurring, household_id), today())
    return Response(
        content, media_type="text/calendar; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="razem-platnosci.ics"'}
    )


def receipt_data(db, receipt):
    return dict(
        **serialize(receipt),
        items=[
            serialize(i)
            for i in db.scalars(
                select(ReceiptItem)
                .where(ReceiptItem.receipt_id == receipt.id, ReceiptItem.household_id == receipt.household_id)
                .order_by(ReceiptItem.position)
            )
        ],
    )


@app.post("/households/{household_id}/receipts", status_code=201)
def receipt_upload(
    household_id: str,
    member: Membership,
    db: Db,
    file: UploadFile = File(...),
    key: Annotated[str | None, Header(alias="Idempotency-Key", min_length=8, max_length=100)] = None,
):
    raw = file.file.read(MAX_IMAGE_BYTES + 1)
    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "Zdjęcie może mieć najwyżej 10 MB.")
    image_hash = hashlib.sha256(raw).hexdigest()
    signature = fingerprint("receipts", {"image_hash": image_hash})
    if key:
        # Only retries of this operation wait for OCR. Other household writes
        # stay available; the transaction-scoped lock also covers provider failure.
        lock_id = int.from_bytes(hashlib.sha256(f"{household_id}:{key}".encode()).digest()[:8], signed=True)
        db.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": lock_id})
        old = db.scalar(select(Mutation).where(Mutation.household_id == household_id, Mutation.key == key))
        if old:
            if old.request_hash != signature:
                raise HTTPException(409, "Ten zapis już istnieje z innymi danymi. Odśwież formularz.")
            return receipt_data(db, scoped(db, Receipt, household_id, old.entity_id))
    rate_limit(f"receipts:{member.user_id}", 12, 3600)
    rate_limit("receipt-service", 60, 3600)
    try:
        image = validated_image(raw)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    categories = [dict(id=c.id, name=c.name, group=c.group) for c in records(db, Category, household_id) if not c.archived]
    filename = secrets.token_hex(24) + ".png"
    destination = storage_path(filename)
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination.write_bytes(image)
    destination.chmod(0o600)
    committed = False
    try:
        receipt = Receipt(
            household_id=household_id,
            path=filename,
            image_hash=image_hash,
            created_by=member.user_id,
            provider=settings.receipt_provider,
        )
        db.add(receipt)
        try:
            extraction = provider().extract(raw if settings.receipt_provider == "fixture" else image, categories)
        except Exception as exc:
            logger.warning(
                "Receipt extraction failed (provider=%s, kind=%s, status=%s)",
                settings.receipt_provider,
                type(exc).__name__,
                getattr(getattr(exc, "response", None), "status_code", None),
            )
            # Only external extraction failure becomes a recoverable draft.
            # Database failures must roll back, never masquerade as OCR failures.
            extraction = None
        complete, ambiguous = False, False
        if extraction is None:
            receipt.status = "failed"
            receipt.error = "Odczyt się nie powiódł. Zdjęcie jest zapisane — uzupełnij dane ręcznie."
        else:
            if settings.receipt_provider == "fixture" and not extraction.items:
                receipt.provider = "manual"
            receipt.merchant, receipt.date, receipt.total = extraction.merchant, extraction.date, extraction.total
            valid_ids = {c["id"] for c in categories}
            rules = records(db, ClassificationRule, household_id)
            category_totals = defaultdict(int)
            db.flush()
            for index, item in enumerate(extraction.items):
                category_id, confidence = classify(db, household_id, item.name, extraction.merchant, rules=rules, active=valid_ids)
                if not category_id:
                    category_id, confidence = (item.category_id, item.confidence) if item.category_id in valid_ids else (None, 0)
                if category_id and item.amount is not None:
                    category_totals[category_id] += item.amount
                ambiguous |= category_id is None or confidence < round(settings.classification_review_threshold * 100)
                db.add(
                    ReceiptItem(
                        household_id=household_id,
                        receipt_id=receipt.id,
                        name=item.name,
                        quantity=item.quantity or "",
                        amount=item.amount,
                        category_id=category_id,
                        confidence=confidence,
                        position=index,
                        created_by=member.user_id,
                    )
                )
            ambiguous |= any(amount < 0 for amount in category_totals.values())
            complete = bool(
                extraction.merchant
                and extraction.date
                and extraction.total
                and extraction.items
                and all(i.amount is not None for i in extraction.items)
                and sum(i.amount for i in extraction.items if i.amount is not None) == extraction.total
            )
            receipt.status = "ready" if complete else "draft"
            if not complete:
                receipt.error = "Uzupełnij dane paragonu. Nie udało się odczytać wszystkich informacji."
        db.flush()
        db.add(
            ReviewTask(
                household_id=household_id,
                receipt_id=receipt.id,
                kind="extraction" if not complete else "classification" if ambiguous else "confirmation",
                title=receipt.merchant or "Paragon do uzupełnienia",
                created_by=member.user_id,
            )
        )
        if duplicate_receipt(db, household_id, receipt, receipt.merchant, receipt.date, receipt.total):
            db.add(
                ReviewTask(
                    household_id=household_id,
                    receipt_id=receipt.id,
                    kind="duplicate",
                    title="Ten paragon może już być zapisany",
                    created_by=member.user_id,
                )
            )
        if key:
            db.add(
                Mutation(
                    household_id=household_id,
                    key=key,
                    resource="receipts",
                    request_hash=signature,
                    entity_id=receipt.id,
                    created_by=member.user_id,
                )
            )
        db.commit()
        committed = True
        return receipt_data(db, receipt)
    finally:
        if not committed:
            destination.unlink(missing_ok=True)


def duplicate_receipt(db, household_id, receipt, merchant, date, total, *, confirmed_only=False):
    matches = Receipt.image_hash == receipt.image_hash
    if merchant and date and total:
        matches = or_(matches, and_(func.lower(Receipt.merchant) == merchant.strip().lower(), Receipt.date == date, Receipt.total == total))
    query = select(Receipt.id).where(Receipt.household_id == household_id, Receipt.id != receipt.id, matches)
    if confirmed_only:
        query = query.where(Receipt.status == "confirmed")
    return db.scalar(query.limit(1))


@app.get("/households/{household_id}/receipts/{receipt_id}")
def receipt_read(household_id: str, receipt_id: str, member: Membership, db: Db):
    return receipt_data(db, scoped(db, Receipt, household_id, receipt_id))


@app.get("/households/{household_id}/receipts/{receipt_id}/image")
def receipt_image(household_id: str, receipt_id: str, member: Membership, db: Db):
    receipt = scoped(db, Receipt, household_id, receipt_id)
    path = storage_path(receipt.path)
    if not path.is_file():
        raise HTTPException(404, "Zdjęcie jest niedostępne.")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "no-store"})


def replace_items(db, receipt, data, member):
    for item in data.items:
        if item.category_id:
            category = scoped(db, Category, member.household_id, item.category_id)
            if category.archived:
                raise HTTPException(422, "Wybierz aktywną kategorię.")
    receipt.merchant, receipt.date, receipt.total = data.merchant, data.date, data.total
    receipt.updated_by = member.user_id
    db.execute(delete(ReceiptItem).where(ReceiptItem.receipt_id == receipt.id, ReceiptItem.household_id == member.household_id))
    for index, item in enumerate(data.items):
        db.add(
            ReceiptItem(
                **item.model_dump(), position=index, receipt_id=receipt.id, household_id=member.household_id, created_by=member.user_id
            )
        )


@app.put("/households/{household_id}/receipts/{receipt_id}")
def receipt_draft(household_id: str, receipt_id: str, data: DraftReceiptInput, member: Membership, db: Db):
    receipt = scoped(db, Receipt, household_id, receipt_id, lock=True)
    if receipt.status == "confirmed":
        raise HTTPException(409, "Ten paragon został już zatwierdzony.")
    replace_items(db, receipt, data, member)
    receipt.status = "draft"
    receipt.error = None
    complete = bool(
        data.merchant
        and data.date
        and data.total
        and data.items
        and all(i.name and i.amount is not None for i in data.items)
        and sum(i.amount for i in data.items if i.amount is not None) == data.total
    )
    duplicate = bool(duplicate_receipt(db, household_id, receipt, data.merchant, data.date, data.total))
    has_duplicate_task = False
    for task in db.scalars(select(ReviewTask).where(ReviewTask.household_id == household_id, ReviewTask.receipt_id == receipt.id)):
        if task.kind != "duplicate":
            task.kind = "confirmation" if complete else "extraction"
            task.title = data.merchant or "Paragon do uzupełnienia"
            task.updated_by = member.user_id
        else:
            has_duplicate_task = True
            task.resolved = not duplicate
            task.updated_by = member.user_id
    if duplicate and not has_duplicate_task:
        db.add(
            ReviewTask(
                household_id=household_id,
                receipt_id=receipt.id,
                kind="duplicate",
                title="Ten paragon może już być zapisany",
                created_by=member.user_id,
            )
        )
    db.commit()
    return receipt_data(db, receipt)


@app.post("/households/{household_id}/receipts/{receipt_id}/finalize")
def receipt_finalize(household_id: str, receipt_id: str, data: FinalizeInput, member: Membership, db: Db):
    # Consistent lock order: household before receipt, then transaction.
    db.scalar(select(Household).where(Household.id == household_id).with_for_update())
    receipt = scoped(db, Receipt, household_id, receipt_id, lock=True)
    if receipt.transaction_id:
        return transaction_data(db, scoped(db, Transaction, household_id, receipt.transaction_id))
    if sum(i.amount for i in data.items) != data.total:
        raise HTTPException(422, "Suma pozycji nie zgadza się z kwotą paragonu. Popraw odczyt przed zapisem.")
    if any(
        not i.category_id or (i.confidence < round(settings.classification_auto_threshold * 100) and not i.reviewed) for i in data.items
    ):
        raise HTTPException(422, "Sprawdź wyróżnione pozycje i wybierz ich kategorie.")
    duplicate = duplicate_receipt(db, household_id, receipt, data.merchant, data.date, data.total, confirmed_only=True)
    if duplicate and not data.acknowledge_duplicate:
        raise HTTPException(409, "Ten paragon może już być zapisany. Potwierdź, że to osobny zakup.")
    replace_items(db, receipt, data, member)
    totals = defaultdict(int)
    for item in data.items:
        totals[item.category_id] += item.amount
        if item.reviewed and item.amount > 0:
            learn(db, household_id, item.name, item.category_id, member.user_id)
    if any(amount < 0 for amount in totals.values()):
        raise HTTPException(422, "Przypisz rabat do kategorii zakupów, których dotyczy. Rabat nie może przekraczać ich kwoty.")
    tx_data = TransactionInput(
        kind="expense",
        amount=data.total,
        date=data.date,
        description=data.merchant,
        account_id=data.account_id,
        allocations=[SplitInput(category_id=k, amount=v) for k, v in totals.items() if v > 0],
    )
    tx = create_transaction(db, member, tx_data, f"receipt:{receipt.id}", source="receipt", source_id=receipt.id)
    receipt.transaction_id, receipt.status, receipt.error = tx.id, "confirmed", None
    for task in db.scalars(select(ReviewTask).where(ReviewTask.household_id == household_id, ReviewTask.receipt_id == receipt.id)):
        task.resolved = True
        task.updated_by = member.user_id
    audit(db, member, "receipt.confirmed", receipt.id)
    db.commit()
    return transaction_data(db, tx)


@app.delete("/households/{household_id}/receipts/{receipt_id}")
def receipt_discard(household_id: str, receipt_id: str, member: Membership, db: Db):
    receipt = scoped(db, Receipt, household_id, receipt_id, lock=True)
    if receipt.status == "confirmed":
        raise HTTPException(409, "Nie możesz usunąć zatwierdzonego paragonu.")
    path = storage_path(receipt.path)
    db.delete(receipt)
    db.commit()
    path.unlink(missing_ok=True)
    return {"ok": True}


@app.delete("/households/{household_id}/rules/{rule_id}")
def rule_delete(household_id: str, rule_id: str, member: Membership, db: Db):
    db.delete(scoped(db, ClassificationRule, household_id, rule_id))
    db.commit()
    return {"ok": True}


@app.get("/households/{household_id}/analytics")
def analytics(household_id: str, month: str, member: Membership, db: Db):
    budget = budget_data(db, household_id, month)
    start, end = month_dates(month)
    current = today()
    elapsed = current.day if start <= current <= end else end.day if current > end else 0
    recurring = recurring_data(db, household_id, month)
    outstanding = sum(r["amount"] for r in recurring if r["active"] and r["scheduled"] and not r["paid"])
    recurring_actual = sum(
        db.scalars(
            select(Transaction.amount).where(
                Transaction.household_id == household_id,
                Transaction.source == "recurring",
                Transaction.date >= start,
                Transaction.date <= end,
            )
        )
    )
    variable = max(0, budget["expenses"] - recurring_actual)
    forecast = (variable * end.day // elapsed + recurring_actual + outstanding + budget["pocket"] + budget["savings"]) if elapsed else None
    trend = []
    index = start.year * 12 + start.month - 1
    for delta in range(5, -1, -1):
        cursor = index - delta
        if cursor // 12 < 2000:
            continue
        m = f"{cursor // 12:04}-{cursor % 12 + 1:02}"
        data = budget_data(db, household_id, m)
        trend.append(
            dict(
                month=m,
                planned=data["planned_income"],
                spent=data["expenses"] + data["pocket"],
                savings=data["savings"],
                income=data["income"],
            )
        )
    return dict(
        budget=budget,
        forecast=forecast,
        forecast_remaining=budget["planned_income"] - forecast if forecast is not None else None,
        elapsed_days=elapsed,
        days_in_month=end.day,
        outstanding_recurring=outstanding,
        recurring_actual=recurring_actual,
        trend=trend,
        savings_rate=budget["savings"] * 100 // budget["income"] if budget["income"] else None,
    )


@app.get("/households/{household_id}/export")
def export(household_id: str, member: Membership, db: Db):
    models = [
        Member,
        Account,
        Category,
        Period,
        BudgetAllocation,
        IncomeSource,
        Transaction,
        TransactionAllocation,
        Goal,
        Recurring,
        Receipt,
        ReceiptItem,
        ClassificationRule,
        ReviewTask,
        Audit,
    ]
    data = {
        "household": serialize(db.get(Household, household_id)),
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "currency": "PLN",
        "money_unit": "grosz",
        "account_money_unit": "1/100 of each account currency",
    }
    for model in models:
        data[model.__tablename__] = [serialize(r) for r in records(db, model, household_id)]
    return data


@app.delete("/households/{household_id}")
def household_delete(household_id: str, data: HouseholdInput, member: Membership, db: Db):
    household = db.get(Household, household_id)
    if member.role != "owner":
        raise HTTPException(403, "Tylko właściciel może usunąć gospodarstwo.")
    if data.name != household.name:
        raise HTTPException(422, "Wpisz dokładną nazwę gospodarstwa.")
    paths = [storage_path(r.path) for r in records(db, Receipt, household_id)]
    # Delete in dependency order to preserve FK integrity.
    for model in [
        ReviewTask,
        ReceiptItem,
        Receipt,
        TransactionAllocation,
        Transaction,
        Recurring,
        ClassificationRule,
        BudgetAllocation,
        IncomeSource,
        Period,
        Goal,
        Category,
        Account,
        Invitation,
        Audit,
        Mutation,
        Member,
    ]:
        db.execute(delete(model).where(model.household_id == household_id))
    db.delete(household)
    db.commit()
    for path in paths:
        path.unlink(missing_ok=True)
    return {"ok": True}


@app.post("/auth/demo")
def demo(request: Request, response: Response, db: Db):
    if settings.app_env != "development":
        raise HTTPException(404, "Nie znaleziono.")
    rate_limit(f"auth:{request.client.host}", 15)
    user = db.scalar(select(User).where(User.email == "roch@demo.local"))
    if not user:
        raise HTTPException(404, "Dane demo nie są dostępne. Uruchom skrypt seed.")
    set_session(db, user, response)
    db.commit()
    return serialize(user)


@app.get("/config")
def public_config():
    return {"demo_enabled": settings.app_env == "development"}
