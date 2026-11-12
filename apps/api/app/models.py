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


class InventoryItem(Scoped, Base):
    __tablename__ = "inventory_items"
    name: Mapped[str] = mapped_column(String(120))
    quantity: Mapped[int] = mapped_column(BigInteger)
    unit: Mapped[str] = mapped_column(String(12))
    location: Mapped[str] = mapped_column(String(12))
    expires_on: Mapped[DateValue | None] = mapped_column(Date, nullable=True)
    minimum: Mapped[int] = mapped_column(BigInteger, default=0)
    __table_args__ = (
        CheckConstraint("quantity between 0 and 1000000000 and minimum between 0 and 1000000000"),
        CheckConstraint("unit in ('szt','kg','g','l','ml','opak')"),
        CheckConstraint("location in ('fridge','freezer','pantry','cupboard')"),
    )


class ShoppingItem(Scoped, Base):
    __tablename__ = "shopping_items"
    name: Mapped[str] = mapped_column(String(120))
    quantity: Mapped[int] = mapped_column(BigInteger)
    unit: Mapped[str] = mapped_column(String(12))
    location: Mapped[str] = mapped_column(String(12))
    estimated_amount: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    category_id: Mapped[str | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="pending")
    purchased_on: Mapped[DateValue | None] = mapped_column(Date, nullable=True)
    actual_amount: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    merchant: Mapped[str] = mapped_column(String(120), default="")
    receipt_item_id: Mapped[str | None] = mapped_column(ForeignKey("receipt_items.id"), nullable=True, unique=True)
    inventory_id: Mapped[str | None] = mapped_column(ForeignKey("inventory_items.id", ondelete="SET NULL"), nullable=True)
    __table_args__ = (
        CheckConstraint("quantity between 1 and 1000000000"),
        CheckConstraint("unit in ('szt','kg','g','l','ml','opak')"),
        CheckConstraint("location in ('fridge','freezer','pantry','cupboard')"),
        CheckConstraint("estimated_amount is null or estimated_amount between 0 and 100000000000"),
        CheckConstraint("actual_amount is null or actual_amount between 0 and 100000000000"),
        CheckConstraint("(status = 'pending' and purchased_on is null) or (status = 'bought' and purchased_on is not null)"),
    )


class User(Record, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(300))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class PasswordResetEvent(Record, Base):
    __tablename__ = "password_reset_events"
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    target_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


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


class MCPConnection(Scoped, Base):
    __tablename__ = "mcp_connections"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    access: Mapped[str] = mapped_column(String(10))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (CheckConstraint("access in ('read','write')"),)


class Account(Scoped, Base):
    __tablename__ = "accounts"
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(20), default="checking")
    currency: Mapped[str] = mapped_column(String(3), default="PLN", server_default="PLN")
    opening_balance: Mapped[int] = mapped_column(BigInteger, default=0)
    __table_args__ = (
        CheckConstraint("kind in ('checking','cash','savings')"),
        CheckConstraint("currency in ('PLN','EUR','USD','GBP','CHF')", name="accounts_currency"),
    )


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
    buffer_category_id: Mapped[str | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    __table_args__ = (UniqueConstraint("household_id", "month"), CheckConstraint("planned_income >= 0"))


class IncomeSource(Scoped, Base):
    __tablename__ = "income_sources"
    period_id: Mapped[str] = mapped_column(ForeignKey("periods.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    member_id: Mapped[str | None] = mapped_column(ForeignKey("members.id"))
    amount: Mapped[int] = mapped_column(BigInteger)
    position: Mapped[int] = mapped_column(Integer)
    __table_args__ = (
        UniqueConstraint("period_id", "position"),
        CheckConstraint("amount between 0 and 100000000000"),
        CheckConstraint("position >= 0"),
    )


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
    frequency: Mapped[str] = mapped_column(String(12), default="monthly", server_default="monthly")
    start_date: Mapped[DateValue | None] = mapped_column(Date, nullable=True)
    reminder_days: Mapped[int] = mapped_column(Integer, default=3, server_default="3")
    category_id: Mapped[str] = mapped_column(ForeignKey("categories.id"))
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (
        CheckConstraint("amount > 0 and day between 1 and 31"),
        CheckConstraint("frequency in ('weekly','monthly','quarterly','yearly')", name="recurring_frequency"),
        CheckConstraint("reminder_days between 0 and 30", name="recurring_reminder_days"),
        CheckConstraint("frequency = 'monthly' or start_date is not null", name="recurring_anchor"),
    )


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
    refund_of_id: Mapped[str | None] = mapped_column(
        ForeignKey("transactions.id", deferrable=True, initially="DEFERRED"), nullable=True, index=True
    )
    bank_match_excluded: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
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
        CheckConstraint(
            "refund_of_id is null or (kind = 'income' and destination_id is null and refund_of_id != id)", name="transaction_refund_shape"
        ),
    )


class AccountAdjustment(Scoped, Base):
    __tablename__ = "account_adjustments"
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    amount: Mapped[int] = mapped_column(BigInteger)
    balance_before: Mapped[int] = mapped_column(BigInteger)
    balance_after: Mapped[int] = mapped_column(BigInteger)
    bank_balance_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint("amount != 0 and balance_after - balance_before = amount"),)


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


class Meter(Scoped, Base):
    __tablename__ = "meters"
    name: Mapped[str] = mapped_column(String(80))
    unit: Mapped[str] = mapped_column(String(8))
    interval_days: Mapped[int] = mapped_column(Integer, default=30)
    __table_args__ = (CheckConstraint("unit in ('kWh','m3','GJ')"), CheckConstraint("interval_days between 0 and 365"))


class MeterPhoto(Scoped, Base):
    __tablename__ = "meter_photos"
    meter_id: Mapped[str] = mapped_column(ForeignKey("meters.id", ondelete="CASCADE"), index=True)
    path: Mapped[str] = mapped_column(String(200))
    image_hash: Mapped[str] = mapped_column(String(64))
    key: Mapped[str] = mapped_column(String(100))
    provider: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(120))
    proposal: Mapped[dict | None] = mapped_column(JSON(), nullable=True)
    diagnostics: Mapped[dict] = mapped_column(JSON(), default=dict)
    __table_args__ = (UniqueConstraint("meter_id", "key"),)


class MeterReading(Scoped, Base):
    __tablename__ = "meter_readings"
    meter_id: Mapped[str] = mapped_column(ForeignKey("meters.id", ondelete="CASCADE"), index=True)
    date: Mapped[DateValue] = mapped_column(Date)
    time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    activities: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    note: Mapped[str] = mapped_column(String(240), default="", server_default="")
    value: Mapped[int] = mapped_column(BigInteger)
    photo_id: Mapped[str | None] = mapped_column(ForeignKey("meter_photos.id", ondelete="SET NULL"), nullable=True)
    __table_args__ = (UniqueConstraint("meter_id", "date"), CheckConstraint("value between 0 and 1000000000000"))


class ReceiptOCRAttempt(Scoped, Base):
    __tablename__ = "receipt_ocr_attempts"
    receipt_id: Mapped[str] = mapped_column(ForeignKey("receipts.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(100))
    provider: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(20))
    diagnostics: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    receipt_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        UniqueConstraint("receipt_id", "key"),
        CheckConstraint("status in ('succeeded','partial','failed')"),
    )


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


class BankConnection(Scoped, Base):
    __tablename__ = "bank_connections"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    state_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    state_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    session_cipher: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    next_sync: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    sync_diagnostic: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)


class BankAccount(Scoped, Base):
    __tablename__ = "bank_accounts"
    connection_id: Mapped[str] = mapped_column(ForeignKey("bank_connections.id", ondelete="CASCADE"), index=True)
    uid_cipher: Mapped[str] = mapped_column(String(2048))
    identity_hash: Mapped[str] = mapped_column(String(64))
    last4: Mapped[str] = mapped_column(String(4))
    currency: Mapped[str] = mapped_column(String(3))
    iban_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    account_id: Mapped[str | None] = mapped_column(ForeignKey("accounts.id"), nullable=True, unique=True)
    start_date: Mapped[DateValue | None] = mapped_column(Date, nullable=True)
    balance: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    balance_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint("household_id", "identity_hash"),)


class BankEntry(Scoped, Base):
    __tablename__ = "bank_entries"
    bank_account_id: Mapped[str] = mapped_column(ForeignKey("bank_accounts.id", ondelete="CASCADE"), index=True)
    reference_hash: Mapped[str] = mapped_column(String(64))
    reliable: Mapped[bool] = mapped_column(Boolean)
    counterparty_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    amount: Mapped[int] = mapped_column(BigInteger)
    date: Mapped[DateValue] = mapped_column(Date)
    description: Mapped[str] = mapped_column(String(160))
    transaction_id: Mapped[str | None] = mapped_column(ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True, index=True)
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    match_method: Mapped[str | None] = mapped_column(String(16), nullable=True)
    auto_refund_eligible: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    __table_args__ = (UniqueConstraint("bank_account_id", "reference_hash"), CheckConstraint("amount != 0"))


class BankSubscription(Scoped, Base):
    __tablename__ = "bank_subscriptions"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    endpoint_hash: Mapped[str] = mapped_column(String(64))
    payload_cipher: Mapped[str] = mapped_column(String(8192))
    __table_args__ = (UniqueConstraint("user_id", "endpoint_hash"),)


class BankDelivery(Scoped, Base):
    __tablename__ = "bank_deliveries"
    subscription_id: Mapped[str] = mapped_column(ForeignKey("bank_subscriptions.id", ondelete="CASCADE"))
    entry_id: Mapped[str] = mapped_column(ForeignKey("bank_entries.id", ondelete="CASCADE"))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint("subscription_id", "entry_id"),)


class Mutation(Scoped, Base):
    __tablename__ = "mutations"
    key: Mapped[str] = mapped_column(String(100))
    resource: Mapped[str] = mapped_column(String(40))
    request_hash: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(36))
    __table_args__ = (UniqueConstraint("household_id", "key"),)


class BudgetSettlement(Scoped, Base):
    __tablename__ = "budget_settlements"
    source_month: Mapped[str] = mapped_column(String(7))
    target_month: Mapped[str] = mapped_column(String(7))
    request_hash: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint("household_id", "source_month"),)


class SurplusPolicy(Scoped, Base):
    __tablename__ = "surplus_policies"
    targets: Mapped[list] = mapped_column(JSON)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    __table_args__ = (UniqueConstraint("household_id"),)
