"""Close a funded past month exactly once, without inventing income."""

from datetime import date, datetime, timezone
from typing import Literal

from fastapi import HTTPException
from pydantic import Field, model_validator
from sqlalchemy import select

from .domain import account_data, audit, budget_data, create_transaction, fingerprint, month_valid, pln_account, records, scoped, today
from .models import BudgetSettlement, Category, Goal, Household, Period, Recurring, SurplusPolicy
from .schedules import unpaid_period
from .schemas import Money, Schema, TransactionInput


class EnvelopeAmount(Schema):
    category_id: str
    amount: Money


class SurplusTarget(Schema):
    account_id: str
    goal_id: str | None = None
    basis_points: int = Field(strict=True, gt=0, le=10000)


class SettlementInput(Schema):
    mode: Literal["carry", "distribute"]
    envelopes: list[EnvelopeAmount] = Field(min_length=1, max_length=150)
    account_id: str | None = None
    transfer_date: date | None = None
    targets: list[SurplusTarget] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def valid(self):
        if len({r.category_id for r in self.envelopes}) != len(self.envelopes):
            raise ValueError("Duplicate envelopes")
        if self.mode == "distribute":
            if not self.account_id or not self.transfer_date or not self.targets or sum(r.basis_points for r in self.targets) != 10000:
                raise ValueError("Distribution requires account, date and 100%")
            if len({(r.account_id, r.goal_id) for r in self.targets}) != len(self.targets):
                raise ValueError("Duplicate targets")
        elif self.account_id or self.targets or self.transfer_date:
            raise ValueError("Carry is not a transfer")
        return self


class SettlementConfirm(SettlementInput):
    preview_token: str = Field(min_length=64, max_length=64)
    transfers_performed: bool = False


def ensure_open(db, household_id, month):
    if db.scalar(select(BudgetSettlement.id).where(BudgetSettlement.household_id == household_id, BudgetSettlement.source_month == month)):
        raise HTTPException(409, "Ten miesiąc został rozliczony. Jego plan i transakcje są zamknięte.")


def ensure_schedule_payable(db, household_id, row):
    if not row.active:
        return
    closed_months = db.scalars(select(BudgetSettlement.source_month).where(BudgetSettlement.household_id == household_id))
    if any(unpaid_period(db, household_id, [row], month) for month in closed_months):
        raise HTTPException(422, "Harmonogram dodaje nieopłacone płatności do rozliczonego miesiąca. Wybierz późniejszą datę rozpoczęcia.")


def next_month(month):
    month_valid(month)
    index = int(month[:4]) * 12 + int(month[5:])
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def policy(db, household_id):
    row = db.scalar(select(SurplusPolicy).where(SurplusPolicy.household_id == household_id))
    return dict(account_id=row.account_id, targets=row.targets) if row else None


def preview(db, household_id, month, data):
    month_valid(month)
    if month >= today().strftime("%Y-%m"):
        raise HTTPException(422, "Rozliczysz nadwyżkę po zakończeniu miesiąca.")
    ensure_open(db, household_id, month)
    target = next_month(month)
    month_valid(target)
    ensure_open(db, household_id, target)
    budget = budget_data(db, household_id, month)
    if not budget["period"]:
        raise HTTPException(422, "Najpierw zapisz plan miesiąca.")
    if budget["unallocated"]:
        raise HTTPException(422, "Najpierw przypisz kategorie wszystkim wydatkom miesiąca.")
    if any(a["kind"] in ("pocket", "goal") and a["remaining"] > 0 for a in budget["allocations"]):
        raise HTTPException(422, "Najpierw potwierdź zaplanowane kieszonkowe i wpłaty na cele albo popraw plan miesiąca.")
    if unpaid_period(db, household_id, records(db, Recurring, household_id), month):
        raise HTTPException(422, "Najpierw potwierdź zaległe płatności cykliczne z tego miesiąca albo popraw harmonogram.")
    available = max(0, min(budget["remaining"], budget["income"] + budget["carry_in"] - budget["spent"]))
    amounts = {a["reference_id"]: a for a in budget["allocations"] if a["kind"] == "category"}
    envelopes = []
    for entry in data.envelopes:
        category = scoped(db, Category, household_id, entry.category_id)
        row = amounts.get(category.id)
        if category.archived or not row or entry.amount > max(0, row["remaining"]):
            raise HTTPException(422, "Wybrana kwota przekracza saldo aktywnej koperty.")
        if entry.amount:
            envelopes.append(dict(category_id=category.id, label=row["label"], group=row["group"], amount=entry.amount))
    total = sum(r["amount"] for r in envelopes)
    if not total or total > available:
        raise HTTPException(422, "Nadwyżka musi mieścić się w rzeczywistych wpływach po wydatkach. Zmniejsz kwoty lub uzupełnij wpływy.")
    targets = []
    balances = account_data(db, household_id)
    if data.mode == "distribute":
        pln_account(db, household_id, data.account_id)
        if next(b["balance"] for b in balances if b["id"] == data.account_id) < total:
            raise HTTPException(422, "Na koncie źródłowym brakuje pieniędzy na podział nadwyżki.")
        if data.transfer_date.strftime("%Y-%m") != target:
            raise HTTPException(422, "Przelewy nadwyżki zapisz w miesiącu następującym po rozliczanym.")
        parts = [total * row.basis_points // 10000 for row in data.targets]
        order = sorted(range(len(parts)), key=lambda i: (-(total * data.targets[i].basis_points % 10000), i))
        for index in order[: total - sum(parts)]:
            parts[index] += 1
        for entry, amount in zip(data.targets, parts, strict=True):
            account = pln_account(db, household_id, entry.account_id)
            if account.id == data.account_id or account.kind != "savings":
                raise HTTPException(422, "Wybierz inne konto oszczędnościowe PLN.")
            goal = scoped(db, Goal, household_id, entry.goal_id) if entry.goal_id else None
            targets.append(dict(**entry.model_dump(), amount=amount, label=goal.name if goal else account.name))
    result = dict(
        source_month=month,
        target_month=target,
        mode=data.mode,
        total=total,
        envelopes=envelopes,
        targets=targets,
        account_id=data.account_id,
        transfer_date=data.transfer_date.isoformat() if data.transfer_date else None,
        available=available,
    )
    token = fingerprint(
        "settlement.preview",
        dict(
            result=result,
            budget=budget,
            balances=balances,
            input=data.model_dump(mode="json", exclude={"preview_token", "transfers_performed"}),
        ),
    )
    return dict(**result, preview_token=token)


def confirm(db, member, month, data):
    db.scalar(select(Household).where(Household.id == member.household_id).with_for_update())
    signature = fingerprint("settlement.confirm:" + month, data.model_dump(mode="json"))
    existing = db.scalar(
        select(BudgetSettlement).where(BudgetSettlement.household_id == member.household_id, BudgetSettlement.source_month == month)
    )
    if existing:
        if existing.request_hash != signature:
            raise HTTPException(409, "Nadwyżka tego miesiąca jest już rozliczona.")
        return existing.result
    result = preview(db, member.household_id, month, data)
    if result["preview_token"] != data.preview_token:
        raise HTTPException(409, "Salda lub plan zmieniły się. Przygotuj nowy podgląd nadwyżki.")
    if data.mode == "distribute" and not data.transfers_performed:
        raise HTTPException(422, "Potwierdź, że przelewy zostały wykonane.")
    if data.mode == "distribute":
        # Record real transfers first. They reserve source-month money, not new income.
        for index, row in enumerate(result["targets"]):
            if row["amount"]:
                create_transaction(
                    db,
                    member,
                    TransactionInput(
                        kind="saving" if row["goal_id"] else "transfer",
                        amount=row["amount"],
                        date=data.transfer_date,
                        description="Nadwyżka " + month + ": " + row["label"],
                        account_id=data.account_id,
                        destination_id=row["account_id"],
                        goal_id=row["goal_id"],
                    ),
                    f"surplus:{month}:{index}",
                    source="surplus",
                )
        saved = db.scalar(select(SurplusPolicy).where(SurplusPolicy.household_id == member.household_id))
        if not saved:
            saved = SurplusPolicy(household_id=member.household_id, account_id=data.account_id, targets=[], created_by=member.user_id)
            db.add(saved)
        saved.account_id = data.account_id
        saved.targets = [row.model_dump() for row in data.targets]
        saved.updated_by = member.user_id
    else:
        period = db.scalar(select(Period).where(Period.household_id == member.household_id, Period.month == result["target_month"]))
        if not period:
            db.add(Period(household_id=member.household_id, month=result["target_month"], planned_income=0, created_by=member.user_id))
    target_period = db.scalar(select(Period).where(Period.household_id == member.household_id, Period.month == result["target_month"]))
    if target_period:
        target_period.updated_at = datetime.now(timezone.utc)
        target_period.updated_by = member.user_id
    settlement = BudgetSettlement(
        household_id=member.household_id,
        source_month=month,
        target_month=result["target_month"],
        request_hash=signature,
        result=result,
        created_by=member.user_id,
    )
    db.add(settlement)
    db.flush()
    audit(db, member, "budget.settled", settlement.id)
    return result
