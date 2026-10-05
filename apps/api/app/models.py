from datetime import date as DateValue
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def uid():
    return str(uuid4())


def now():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Record:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(36), nullable=True)


class Scoped(Record):
    household_id: Mapped[str] = mapped_column(ForeignKey("households.id", ondelete="CASCADE"), index=True)


class User(Record, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(300))


class SessionToken(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Household(Record, Base):
    __tablename__ = "households"
    name: Mapped[str] = mapped_column(String(80))


class Member(Scoped, Base):
    __tablename__ = "members"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    role: Mapped[str] = mapped_column(String(20), default="member")
    __table_args__ = (UniqueConstraint("household_id", "user_id"), CheckConstraint("role in ('owner','member')"))


class Invitation(Scoped, Base):
    __tablename__ = "invitations"
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class Account(Scoped, Base):
    __tablename__ = "accounts"
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(20), default="checking")
    opening_balance: Mapped[int] = mapped_column(BigInteger, default=0)
    __table_args__ = (CheckConstraint("kind in ('checking','cash','savings')"),)


class Category(Scoped, Base):
    __tablename__ = "categories"
    name: Mapped[str] = mapped_column(String(80))
    group: Mapped[str] = mapped_column(String(40), default="Potrzeby")
    icon: Mapped[str] = mapped_column(String(30), default="basket")
    color: Mapped[str] = mapped_column(String(20), default="green")
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("household_id", "name"),)


class Period(Scoped, Base):
    __tablename__ = "periods"
    month: Mapped[str] = mapped_column(String(7))
    planned_income: Mapped[int] = mapped_column(BigInteger, default=0)
    __table_args__ = (UniqueConstraint("household_id", "month"), CheckConstraint("planned_income >= 0"))


class BudgetAllocation(Scoped, Base):
    __tablename__ = "budget_allocations"
    period_id: Mapped[str] = mapped_column(ForeignKey("periods.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    reference_id: Mapped[str] = mapped_column(String(36))
    label: Mapped[str] = mapped_column(String(100))
    group: Mapped[str] = mapped_column(String(40))
    amount: Mapped[int] = mapped_column(BigInteger)
    __table_args__ = (
        UniqueConstraint("period_id", "kind", "reference_id"),
        CheckConstraint("amount >= 0"),
        CheckConstraint("kind in ('category','pocket','goal')"),
    )


class Merchant(Scoped, Base):
    __tablename__ = "merchants"
    name: Mapped[str] = mapped_column(String(120))
    __table_args__ = (UniqueConstraint("household_id", "name"),)


class Goal(Scoped, Base):
    __tablename__ = "goals"
    name: Mapped[str] = mapped_column(String(80))
    target: Mapped[int] = mapped_column(BigInteger)
    opening_amount: Mapped[int] = mapped_column(BigInteger, default=0)
    monthly_amount: Mapped[int] = mapped_column(BigInteger, default=0)
    icon: Mapped[str] = mapped_column(String(30), default="flag")
    __table_args__ = (CheckConstraint("target > 0 and opening_amount >= 0 and monthly_amount >= 0"),)


class Recurring(Scoped, Base):
    __tablename__ = "recurring"
    name: Mapped[str] = mapped_column(String(120))
    amount: Mapped[int] = mapped_column(BigInteger)
    day: Mapped[int] = mapped_column(Integer)
    category_id: Mapped[str] = mapped_column(ForeignKey("categories.id"))
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (CheckConstraint("amount > 0 and day between 1 and 31"),)


class Transaction(Scoped, Base):
    __tablename__ = "transactions"
    kind: Mapped[str] = mapped_column(String(20))
    amount: Mapped[int] = mapped_column(BigInteger)
    date: Mapped[DateValue] = mapped_column(Date)
    description: Mapped[str] = mapped_column(String(160))
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    destination_id: Mapped[str | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    member_id: Mapped[str | None] = mapped_column(ForeignKey("members.id"), nullable=True)
    goal_id: Mapped[str | None] = mapped_column(ForeignKey("goals.id"), nullable=True)
    merchant_id: Mapped[str | None] = mapped_column(ForeignKey("merchants.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="categorized")
    source: Mapped[str] = mapped_column(String(20), default="manual")
    source_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(100))
    request_hash: Mapped[str] = mapped_column(String(64))
    __table_args__ = (
        UniqueConstraint("household_id", "idempotency_key"),
        CheckConstraint("amount > 0"),
        CheckConstraint("kind in ('expense','income','pocket','transfer','saving')"),
        CheckConstraint("status in ('categorized','unallocated')"),
        CheckConstraint("kind != 'pocket' or member_id is not null"),
        CheckConstraint("kind != 'saving' or (goal_id is not null and destination_id is not null)"),
        CheckConstraint("kind != 'transfer' or destination_id is not null"),
        CheckConstraint("destination_id is null or destination_id != account_id"),
    )


class TransactionAllocation(Scoped, Base):
    __tablename__ = "transaction_allocations"
    transaction_id: Mapped[str] = mapped_column(ForeignKey("transactions.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[str] = mapped_column(ForeignKey("categories.id"))
    amount: Mapped[int] = mapped_column(BigInteger)
    __table_args__ = (UniqueConstraint("transaction_id", "category_id"), CheckConstraint("amount > 0"))


class Receipt(Scoped, Base):
    __tablename__ = "receipts"
    merchant: Mapped[str] = mapped_column(String(120), default="")
    date: Mapped[DateValue | None] = mapped_column(Date, nullable=True)
    total: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    path: Mapped[str] = mapped_column(String(200))
    image_hash: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    provider: Mapped[str] = mapped_column(String(20), default="manual")
    error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    transaction_id: Mapped[str | None] = mapped_column(ForeignKey("transactions.id", ondelete="SET NULL"), unique=True, nullable=True)
    __table_args__ = (CheckConstraint("total is null or total > 0"), CheckConstraint("status in ('draft','ready','confirmed','failed')"))


class ReceiptItem(Scoped, Base):
    __tablename__ = "receipt_items"
    receipt_id: Mapped[str] = mapped_column(ForeignKey("receipts.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    quantity: Mapped[str] = mapped_column(String(30), default="1")
    amount: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    category_id: Mapped[str | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    confidence: Mapped[int] = mapped_column(Integer, default=0)
    position: Mapped[int] = mapped_column(Integer)
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (
        CheckConstraint(
            "(amount is null or amount between -100000000000 and 100000000000) and confidence between 0 and 100",
            name="ck_receipt_item_draft_amount",
        ),
    )


class ClassificationRule(Scoped, Base):
    __tablename__ = "classification_rules"
    pattern: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(20), default="normalized")
    category_id: Mapped[str] = mapped_column(ForeignKey("categories.id"))
    __table_args__ = (UniqueConstraint("household_id", "kind", "pattern"), CheckConstraint("kind in ('exact','normalized','merchant')"))


class ReviewTask(Scoped, Base):
    __tablename__ = "review_tasks"
    kind: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(160))
    receipt_id: Mapped[str | None] = mapped_column(ForeignKey("receipts.id", ondelete="CASCADE"), nullable=True)
    transaction_id: Mapped[str | None] = mapped_column(ForeignKey("transactions.id", ondelete="CASCADE"), nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (
        CheckConstraint("kind in ('classification','extraction','duplicate','unallocated','confirmation')", name="ck_review_task_kind"),
    )


class Audit(Scoped, Base):
    __tablename__ = "audit_events"
    action: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[str] = mapped_column(String(36))
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class Mutation(Scoped, Base):
    __tablename__ = "mutations"
    key: Mapped[str] = mapped_column(String(100))
    resource: Mapped[str] = mapped_column(String(40))
    request_hash: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(36))
    __table_args__ = (UniqueConstraint("household_id", "key"),)
