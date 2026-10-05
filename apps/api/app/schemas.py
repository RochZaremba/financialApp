import re
from datetime import date as DateValue
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

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


class BudgetInput(Schema):
    planned_income: Money
    allocations: list[AllocationInput] = Field(max_length=150)


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
