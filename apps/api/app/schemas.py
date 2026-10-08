import re
from datetime import date as DateValue
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

Money = Annotated[int, Field(strict=True, ge=0, le=100_000_000_000)]
SignedMoney = Annotated[int, Field(strict=True, ge=-100_000_000_000, le=100_000_000_000)]
PositiveMoney = Annotated[int, Field(strict=True, gt=0, le=100_000_000_000)]
Name = Annotated[str, Field(min_length=1, max_length=80)]


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Credentials(Schema):
    email: str = Field(min_length=3, max_length=254)
    password: Annotated[str, StringConstraints(strip_whitespace=False, min_length=10, max_length=128)]
    name: Name = "Domownik"

    @field_validator("email")
    @classmethod
    def email_valid(cls, value):
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Podaj poprawny adres e-mail")
        return value.lower()


class HouseholdInput(Schema):
    name: Name


class JoinInput(Schema):
    token: str = Field(min_length=20, max_length=200)


class CategoryInput(Schema):
    name: Name
    group: Literal["Potrzeby", "Na co dzień"] = "Potrzeby"
    icon: str = Field(default="basket", max_length=30)
    color: str = Field(default="green", max_length=20)


class AllocationInput(Schema):
    kind: Literal["category", "pocket", "goal"]
    reference_id: str
    amount: Money


class IncomeSourceInput(Schema):
    name: Name
    member_id: str | None = Field(default=None, min_length=1, max_length=36)
    amount: Money


class BudgetInput(Schema):
    planned_income: Money | None = None
    income_sources: list[IncomeSourceInput] | None = Field(default=None, max_length=50)
    allocations: list[AllocationInput] = Field(max_length=150)

    @model_validator(mode="after")
    def income_valid(self):
        if self.income_sources is None:
            if self.planned_income is None:
                raise ValueError("Dodaj źródła dochodu.")
            return self
        total = sum(source.amount for source in self.income_sources)
        if total > 100_000_000_000:
            raise ValueError("Łączny dochód jest za duży.")
        if self.planned_income is not None and self.planned_income != total:
            raise ValueError("Łączny dochód musi zgadzać się ze źródłami.")
        return self


class SplitInput(Schema):
    category_id: str
    amount: PositiveMoney


class TransactionInput(Schema):
    kind: Literal["expense", "income", "pocket", "transfer", "saving"]
    amount: PositiveMoney
    date: DateValue
    description: str = Field(min_length=1, max_length=160)
    account_id: str
    destination_id: str | None = None
    member_id: str | None = None
    goal_id: str | None = None
    allocations: list[SplitInput] = Field(default_factory=list, max_length=150)


class GoalInput(Schema):
    name: Name
    target: PositiveMoney
    opening_amount: Money = 0
    monthly_amount: Money = 0
    icon: str = Field(default="flag", max_length=30)


class AccountInput(Schema):
    currency: Literal["PLN", "EUR", "USD", "GBP", "CHF"] = "PLN"
    name: Name
    kind: Literal["checking", "cash", "savings"] = "checking"
    opening_balance: Annotated[int, Field(strict=True, ge=-100_000_000_000, le=100_000_000_000)] = 0


class RecurringInput(Schema):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    amount: PositiveMoney
    day: Annotated[int, Field(strict=True, ge=1, le=31)]
    category_id: str
    account_id: str
    active: bool = True


class DraftItemInput(Schema):
    name: str = Field(default="", max_length=160)
    quantity: str = Field(default="", max_length=30)
    amount: SignedMoney | None = None
    category_id: str | None = None
    confidence: Annotated[int, Field(strict=True, ge=0, le=100)] = 0
    reviewed: bool = False


class DraftReceiptInput(Schema):
    merchant: str = Field(default="", max_length=120)
    date: DateValue | None = None
    total: PositiveMoney | None = None
    items: list[DraftItemInput] = Field(default_factory=list, max_length=200)


class ItemInput(Schema):
    name: str = Field(min_length=1, max_length=160)
    quantity: str = Field(default="", max_length=30)
    amount: SignedMoney
    category_id: str | None = None
    confidence: Annotated[int, Field(strict=True, ge=0, le=100)] = 0
    reviewed: bool = False


class ReceiptInput(Schema):
    merchant: str = Field(min_length=1, max_length=120)
    date: DateValue
    total: PositiveMoney
    items: list[ItemInput] = Field(min_length=1, max_length=200)


class FinalizeInput(ReceiptInput):
    account_id: str
    acknowledge_duplicate: bool = False


class ExtractedItem(Schema):
    name: str = Field(min_length=1, max_length=160)
    quantity: str | None = Field(max_length=30)
    amount: SignedMoney | None
    category_id: str | None
    confidence: Annotated[int, Field(strict=True, ge=0, le=100)]


class Extraction(Schema):
    merchant: str = Field(max_length=120)
    date: DateValue | None
    total: PositiveMoney | None
    items: list[ExtractedItem] = Field(max_length=200)
