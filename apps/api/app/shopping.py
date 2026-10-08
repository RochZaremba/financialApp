"""Household shopping and stock; quantities are integer thousandths, money grosze."""

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import get_db
from .domain import audit, fingerprint, normalize, scoped, serialize, today
from .models import Category, Household, InventoryItem, Member, Mutation, Receipt, ReceiptItem, ShoppingItem
from .schemas import Money, Schema
from .security import household_member

router = APIRouter(prefix="/households/{household_id}/shopping", tags=["shopping"])
Db = Annotated[Session, Depends(get_db)]
Membership = Annotated[Member, Depends(household_member)]
Key = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=100)]
Quantity = Annotated[int, Field(strict=True, ge=0, le=1_000_000_000)]
PositiveQuantity = Annotated[int, Field(strict=True, gt=0, le=1_000_000_000)]
Unit = Literal["szt", "kg", "g", "l", "ml", "opak"]
Location = Literal["fridge", "freezer", "pantry", "cupboard"]


class ProductInput(Schema):
    name: str = Field(min_length=1, max_length=120)
    quantity: PositiveQuantity
    unit: Unit = "szt"
    location: Location = "pantry"


class ListInput(ProductInput):
    estimated_amount: Money | None = None
    category_id: str | None = None


class Revision(Schema):
    expected_updated_at: datetime


class ListEdit(ListInput, Revision):
    pass


class StockInput(ProductInput):
    quantity: Quantity
    minimum: Quantity = 0
    expires_on: date | None = None

    @field_validator("expires_on")
    @classmethod
    def expiry_valid(cls, value):
        if value and not 2000 <= value.year <= 2100:
            raise ValueError("Wybierz datę pomiędzy 2000 a 2100 rokiem.")
        return value


class StockEdit(StockInput, Revision):
    pass


class Consume(Revision):
    quantity: PositiveQuantity


class Purchase(Revision):
    purchased_on: date
    actual_amount: Money | None = None
    merchant: str = Field(default="", max_length=120)
    add_to_stock: bool = True
    expires_on: date | None = None

    @field_validator("purchased_on")
    @classmethod
    def purchase_valid(cls, value):
        if not 2000 <= value.year <= 2100 or value > today():
            raise ValueError("Wybierz datę zakończonego zakupu.")
        return value

    @field_validator("expires_on")
    @classmethod
    def expiry_valid(cls, value):
        return StockInput.expiry_valid(value)


class ReceiptImport(ProductInput):
    expires_on: date | None = None
    shopping_item_id: str | None = None
    shopping_updated_at: datetime | None = None

    @field_validator("expires_on")
    @classmethod
    def expiry_valid(cls, value):
        return StockInput.expiry_valid(value)


def mutate(db, member, key, resource, data, operation):
    """Serialize stock writes and persist replay results in the same transaction."""
    db.scalar(select(Household).where(Household.id == member.household_id).with_for_update())
    signature = fingerprint(resource, data)
    previous = db.scalar(select(Mutation).where(Mutation.household_id == member.household_id, Mutation.key == key))
    if previous:
        if previous.request_hash != signature:
            raise HTTPException(409, "Ten zapis już istnieje z innymi danymi. Odśwież formularz.")
        if resource.startswith("delete:"):
            return {"ok": True}
        model = InventoryItem if resource.startswith("stock:") else ShoppingItem
        return serialize(scoped(db, model, member.household_id, previous.entity_id))
    row = operation()
    db.flush()
    entity_id = row.id
    db.add(
        Mutation(
            household_id=member.household_id,
            key=key,
            resource=":".join(resource.split(":")[:2]),
            request_hash=signature,
            entity_id=entity_id,
            created_by=member.user_id,
        )
    )
    audit(db, member, resource, entity_id)
    deleting = resource.startswith("delete:")
    result = {"ok": True} if deleting else serialize(row)
    db.commit()
    return result


def revision(row, data):
    if row.updated_at != data.expected_updated_at:
        raise HTTPException(409, "Ktoś zmienił ten produkt. Odśwież listę i spróbuj ponownie.")


def pending(db, member, item_id):
    row = scoped(db, ShoppingItem, member.household_id, item_id)
    if row.status != "pending":
        raise HTTPException(409, "Ten zakup jest już w historii. Dodaj go ponownie do listy.")
    return row


def capacity(db, member, model):
    query = select(func.count()).select_from(model).where(model.household_id == member.household_id)
    if model == ShoppingItem:
        query = query.where(ShoppingItem.status == "pending")
    if db.scalar(query) >= 500:
        raise HTTPException(409, "Masz już 500 produktów. Usuń niepotrzebne pozycje, żeby dodać kolejne.")


def category_valid(db, member, category_id):
    if category_id and scoped(db, Category, member.household_id, category_id).archived:
        raise HTTPException(422, "Wybierz aktywną kategorię.")


def new_stock(db, member, data):
    capacity(db, member, InventoryItem)
    row = InventoryItem(**data, household_id=member.household_id, created_by=member.user_id)
    db.add(row)
    db.flush()
    return row


@router.get("")
def overview(household_id: str, member: Membership, db: Db):
    items = list(
        db.scalars(
            select(ShoppingItem)
            .where(ShoppingItem.household_id == household_id, ShoppingItem.status == "pending")
            .order_by(ShoppingItem.created_at, ShoppingItem.id)
            .limit(500)
        )
    )
    stock = list(
        db.scalars(
            select(InventoryItem)
            .where(InventoryItem.household_id == household_id)
            .order_by(InventoryItem.expires_on.asc().nulls_last(), InventoryItem.name, InventoryItem.id)
            .limit(500)
        )
    )
    available = defaultdict(int)
    minimums = {}
    queued = {(normalize(i.name), i.unit) for i in items}
    for row in stock:
        identity = (normalize(row.name), row.unit, row.location)
        if row.expires_on is None or row.expires_on >= today():
            available[identity] += row.quantity
        if identity not in minimums or row.minimum > minimums[identity].minimum:
            minimums[identity] = row
    suggestions = []
    for identity, row in minimums.items():
        if row.minimum > available[identity] and identity[:2] not in queued:
            suggestions.append(dict(name=row.name, quantity=row.minimum - available[identity], unit=row.unit, location=row.location))
    return {
        "items": [serialize(row) for row in items],
        "stock": [serialize(row) for row in stock],
        "estimated_total": sum(row.estimated_amount or 0 for row in items),
        "unpriced_count": sum(row.estimated_amount is None for row in items),
        "expiring_count": sum(
            row.quantity > 0 and row.expires_on is not None and row.expires_on <= today() + timedelta(days=3) for row in stock
        ),
        "suggestions": suggestions[:30],
        "today": today(),
        "quantity_unit": "1/1000 of declared unit",
    }


@router.post("/items", status_code=201)
def list_create(household_id: str, data: ListInput, member: Membership, db: Db, key: Key):
    def operation():
        category_valid(db, member, data.category_id)
        capacity(db, member, ShoppingItem)
        row = ShoppingItem(**data.model_dump(), household_id=household_id, created_by=member.user_id)
        db.add(row)
        return row

    return mutate(db, member, key, "list:create", data.model_dump(), operation)


@router.put("/items/{item_id}")
def list_edit(household_id: str, item_id: str, data: ListEdit, member: Membership, db: Db, key: Key):
    def operation():
        row = pending(db, member, item_id)
        revision(row, data)
        category_valid(db, member, data.category_id)
        for field, value in data.model_dump(exclude={"expected_updated_at"}).items():
            setattr(row, field, value)
        row.updated_by = member.user_id
        return row

    return mutate(db, member, key, f"list:edit:{item_id}", data.model_dump(), operation)


@router.delete("/items/{item_id}")
def list_delete(household_id: str, item_id: str, data: Revision, member: Membership, db: Db, key: Key):
    def operation():
        row = pending(db, member, item_id)
        revision(row, data)
        db.delete(row)
        return row

    return mutate(db, member, key, f"delete:list:{item_id}", data.model_dump(), operation)


@router.post("/items/{item_id}/purchase")
def purchase(household_id: str, item_id: str, data: Purchase, member: Membership, db: Db, key: Key):
    def operation():
        row = pending(db, member, item_id)
        revision(row, data)
        if data.add_to_stock:
            stock = new_stock(
                db,
                member,
                dict(name=row.name, quantity=row.quantity, unit=row.unit, location=row.location, expires_on=data.expires_on, minimum=0),
            )
            row.inventory_id = stock.id
        row.status, row.purchased_on, row.actual_amount, row.merchant = "bought", data.purchased_on, data.actual_amount, data.merchant
        row.updated_by = member.user_id
        return row

    return mutate(db, member, key, f"list:purchase:{item_id}", data.model_dump(), operation)


@router.post("/stock", status_code=201)
def stock_create(household_id: str, data: StockInput, member: Membership, db: Db, key: Key):
    return mutate(db, member, key, "stock:create", data.model_dump(), lambda: new_stock(db, member, data.model_dump()))


@router.put("/stock/{item_id}")
def stock_edit(household_id: str, item_id: str, data: StockEdit, member: Membership, db: Db, key: Key):
    def operation():
        row = scoped(db, InventoryItem, household_id, item_id)
        revision(row, data)
        for field, value in data.model_dump(exclude={"expected_updated_at"}).items():
            setattr(row, field, value)
        row.updated_by = member.user_id
        return row

    return mutate(db, member, key, f"stock:edit:{item_id}", data.model_dump(), operation)


@router.post("/stock/{item_id}/consume")
def consume(household_id: str, item_id: str, data: Consume, member: Membership, db: Db, key: Key):
    def operation():
        row = scoped(db, InventoryItem, household_id, item_id)
        revision(row, data)
        if data.quantity > row.quantity:
            raise HTTPException(422, "Nie możesz zużyć więcej, niż masz w zapasach.")
        row.quantity -= data.quantity
        row.updated_by = member.user_id
        return row

    return mutate(db, member, key, f"stock:consume:{item_id}", data.model_dump(), operation)


@router.delete("/stock/{item_id}")
def stock_delete(household_id: str, item_id: str, data: Revision, member: Membership, db: Db, key: Key):
    def operation():
        row = scoped(db, InventoryItem, household_id, item_id)
        revision(row, data)
        db.delete(row)
        return row

    return mutate(db, member, key, f"delete:stock:{item_id}", data.model_dump(), operation)


@router.get("/history")
def history(
    household_id: str,
    member: Membership,
    db: Db,
    q: str = Query(default="", max_length=120),
    date_from: date | None = None,
    date_to: date | None = None,
    offset: int = Query(default=0, ge=0, le=1_000_000),
    limit: int = Query(default=30, ge=1, le=100),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "Data od nie może być późniejsza niż data do.")
    conditions = [ShoppingItem.household_id == household_id, ShoppingItem.status == "bought"]
    if q.strip():
        conditions.append(
            ShoppingItem.name.icontains(q.strip(), autoescape=True) | ShoppingItem.merchant.icontains(q.strip(), autoescape=True)
        )
    if date_from:
        conditions.append(ShoppingItem.purchased_on >= date_from)
    if date_to:
        conditions.append(ShoppingItem.purchased_on <= date_to)
    total = db.scalar(select(func.count()).select_from(ShoppingItem).where(*conditions))
    rows = db.scalars(
        select(ShoppingItem)
        .where(*conditions)
        .order_by(ShoppingItem.purchased_on.desc(), ShoppingItem.created_at.desc(), ShoppingItem.id)
        .offset(offset)
        .limit(limit)
    )
    return {"items": [serialize(row) for row in rows], "total": total, "offset": offset, "limit": limit}


@router.get("/receipts")
def receipt_choices(household_id: str, member: Membership, db: Db):
    receipts = list(
        db.scalars(
            select(Receipt)
            .where(Receipt.household_id == household_id, Receipt.status == "confirmed")
            .order_by(Receipt.date.desc(), Receipt.id)
            .limit(20)
        )
    )
    ids = [row.id for row in receipts]
    items = list(
        db.scalars(
            select(ReceiptItem)
            .where(ReceiptItem.household_id == household_id, ReceiptItem.receipt_id.in_(ids), ReceiptItem.amount > 0)
            .order_by(ReceiptItem.position)
        )
    )
    imported = set(
        db.scalars(
            select(ShoppingItem.receipt_item_id).where(
                ShoppingItem.household_id == household_id, ShoppingItem.receipt_item_id.in_([row.id for row in items])
            )
        )
    )
    return [
        dict(
            id=row.id,
            merchant=row.merchant,
            date=row.date,
            items=[dict(**serialize(item), imported=item.id in imported) for item in items if item.receipt_id == row.id],
        )
        for row in receipts
    ]


@router.post("/receipt-items/{item_id}", status_code=201)
def import_receipt(household_id: str, item_id: str, data: ReceiptImport, member: Membership, db: Db, key: Key):
    def operation():
        item = scoped(db, ReceiptItem, household_id, item_id)
        receipt = scoped(db, Receipt, household_id, item.receipt_id)
        if receipt.status != "confirmed" or item.amount is None or item.amount <= 0:
            raise HTTPException(422, "Wybierz produkt z zatwierdzonego paragonu, bez pozycji rabatowych.")
        if receipt.date is None or receipt.date > today():
            raise HTTPException(422, "Data zakupu na paragonie musi oznaczać zakończony zakup.")
        if db.scalar(select(ShoppingItem.id).where(ShoppingItem.receipt_item_id == item_id)):
            raise HTTPException(409, "Ten produkt z paragonu jest już w zapasach i historii.")
        row = (
            pending(db, member, data.shopping_item_id)
            if data.shopping_item_id
            else ShoppingItem(household_id=household_id, created_by=member.user_id)
        )
        if data.shopping_item_id and row.updated_at != data.shopping_updated_at:
            raise HTTPException(409, "Ktoś zmienił produkt na liście. Odśwież i wybierz go ponownie.")
        stock = new_stock(db, member, dict(**data.model_dump(exclude={"shopping_item_id", "shopping_updated_at"}), minimum=0))
        row.name, row.quantity, row.unit, row.location = data.name, data.quantity, data.unit, data.location
        row.status, row.purchased_on, row.actual_amount = "bought", receipt.date, item.amount
        row.category_id, row.merchant, row.receipt_item_id, row.inventory_id = item.category_id, receipt.merchant, item.id, stock.id
        row.updated_by = member.user_id
        db.add(row)
        return row

    return mutate(db, member, key, f"list:receipt:{item_id}", data.model_dump(), operation)
