"""Private meter photographs, reviewed readings and exact usage intervals."""

import hashlib
import os
import secrets
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .domain import audit, create_record, creator_names, scoped, serialize, today
from .meter_vision import extract_meter
from .models import Household, Member, Meter, MeterPhoto, MeterReading, Mutation
from .ocr import error_details
from .receipts import MAX_IMAGE_BYTES, storage_path, validated_image
from .schemas import Name, Schema
from .security import household_member, rate_limit

router = APIRouter(prefix="/households/{household_id}/meters", tags=["meters"])
Db = Annotated[Session, Depends(get_db)]
Membership = Annotated[Member, Depends(household_member)]
Key = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=100)]


class MeterInput(Schema):
    name: Name
    unit: Literal["kWh", "m3", "GJ"]
    interval_days: int = Field(default=30, strict=True, ge=0, le=365)


class PlanInput(Schema):
    interval_days: int = Field(strict=True, ge=0, le=365)
    expected_updated_at: datetime


class ReadingInput(Schema):
    date: date
    value: int = Field(strict=True, ge=0, le=1_000_000_000_000)
    photo_id: str | None = Field(default=None, max_length=36)


class ReadingEdit(ReadingInput):
    expected_updated_at: datetime


class Revision(Schema):
    expected_updated_at: datetime


def locked_meter(db, member, identifier):
    db.scalar(select(Household).where(Household.id == member.household_id).with_for_update())
    return scoped(db, Meter, member.household_id, identifier, lock=True)


def validate_reading(db, meter, data, identifier=None):
    if not 2000 <= data.date.year <= 2100 or data.date > today():
        raise HTTPException(422, "Wybierz datę od 2000 roku, nie późniejszą niż dziś.")
    if data.photo_id and scoped(db, MeterPhoto, meter.household_id, data.photo_id).meter_id != meter.id:
        raise HTTPException(422, "Zdjęcie należy do innego licznika.")
    query = select(MeterReading).where(MeterReading.meter_id == meter.id, MeterReading.household_id == meter.household_id)
    if identifier:
        query = query.where(MeterReading.id != identifier)
    if db.scalar(query.where(MeterReading.date == data.date)):
        raise HTTPException(409, "Ten dzień ma już odczyt. Popraw istniejący wpis.")
    before = db.scalar(query.where(MeterReading.date < data.date).order_by(MeterReading.date.desc()).limit(1))
    after = db.scalar(query.where(MeterReading.date > data.date).order_by(MeterReading.date).limit(1))
    if (before and data.value < before.value) or (after and data.value > after.value):
        raise HTTPException(
            422, "Stan nie pasuje do sąsiednich odczytów. Sprawdź cyfry i datę. Po wymianie lub wyzerowaniu dodaj nowy licznik."
        )


@router.get("")
def meter_list(household_id: str, member: Membership, db: Db):
    latest = (
        select(func.max(MeterReading.date))
        .where(MeterReading.meter_id == Meter.id, MeterReading.household_id == household_id)
        .scalar_subquery()
    )
    return [
        dict(**serialize(meter), last_date=last)
        for meter, last in db.execute(select(Meter, latest).where(Meter.household_id == household_id).order_by(Meter.created_at).limit(30))
    ]


@router.post("", status_code=201)
def meter_create(household_id: str, data: MeterInput, member: Membership, db: Db, key: Key):
    db.scalar(select(Household).where(Household.id == household_id).with_for_update())
    repeated = db.scalar(select(Mutation.id).where(Mutation.household_id == household_id, Mutation.key == key))
    if not repeated and db.scalar(select(func.count()).select_from(Meter).where(Meter.household_id == household_id)) >= 30:
        raise HTTPException(409, "Gospodarstwo może mieć najwyżej 30 liczników.")
    meter = create_record(db, member, Meter, data.model_dump(), key)
    db.commit()
    return serialize(meter)


@router.get("/{meter_id}")
def meter_read(household_id: str, meter_id: str, member: Membership, db: Db):
    meter = scoped(db, Meter, household_id, meter_id)
    rows = list(
        db.scalars(
            select(MeterReading)
            .where(MeterReading.household_id == household_id, MeterReading.meter_id == meter_id)
            .order_by(MeterReading.date.desc())
            .limit(501)
        )
    )
    truncated = len(rows) > 500
    rows = list(reversed(rows[:500]))
    authors = creator_names(db, rows)
    result = []
    previous = None
    for row in rows:
        days = (row.date - previous.date).days if previous else None
        consumed = row.value - previous.value if previous else None
        average = int((Decimal(consumed) / days).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) if days else None
        result.append(
            dict(
                **serialize(row),
                created_by_name=authors.get(row.created_by),
                consumption=consumed,
                days=days,
                average=average,
                from_date=previous.date if previous else None,
            )
        )
        previous = row
    due = previous.date + timedelta(days=meter.interval_days) if previous and meter.interval_days else None
    photos = list(
        db.scalars(
            select(MeterPhoto)
            .where(MeterPhoto.household_id == household_id, MeterPhoto.meter_id == meter_id)
            .order_by(MeterPhoto.created_at.desc())
            .limit(5)
        )
    )
    return dict(
        meter=serialize(meter),
        readings=result,
        photos=[serialize(photo) for photo in photos],
        truncated=truncated,
        next_due=due,
        overdue=bool(due and due <= today()),
        today=today(),
    )


@router.put("/{meter_id}/plan")
def meter_plan(household_id: str, meter_id: str, data: PlanInput, member: Membership, db: Db):
    meter = locked_meter(db, member, meter_id)
    if meter.updated_at != data.expected_updated_at:
        raise HTTPException(409, "Plan został zmieniony. Odśwież ekran.")
    meter.interval_days, meter.updated_by = data.interval_days, member.user_id
    audit(db, member, "meter.plan", meter.id)
    db.commit()
    return serialize(meter)


@router.post("/{meter_id}/readings", status_code=201)
def reading_create(household_id: str, meter_id: str, data: ReadingInput, member: Membership, db: Db, key: Key):
    meter = locked_meter(db, member, meter_id)
    row = create_record(db, member, MeterReading, dict(**data.model_dump(), meter_id=meter_id), key)
    validate_reading(db, meter, data, row.id)
    db.commit()
    return serialize(row)


@router.put("/{meter_id}/readings/{reading_id}")
def reading_edit(household_id: str, meter_id: str, reading_id: str, data: ReadingEdit, member: Membership, db: Db):
    meter = locked_meter(db, member, meter_id)
    row = scoped(db, MeterReading, household_id, reading_id, lock=True)
    if row.meter_id != meter.id:
        raise HTTPException(404, "Nie znaleziono odczytu tego licznika.")
    if row.updated_at != data.expected_updated_at:
        raise HTTPException(409, "Odczyt został zmieniony. Odśwież ekran przed poprawką.")
    validate_reading(db, meter, data, row.id)
    for key, value in data.model_dump(exclude={"expected_updated_at"}).items():
        setattr(row, key, value)
    row.updated_by = member.user_id
    audit(db, member, "meter.reading.edited", row.id)
    db.commit()
    return serialize(row)


@router.delete("/{meter_id}/readings/{reading_id}")
def reading_delete(household_id: str, meter_id: str, reading_id: str, data: Revision, member: Membership, db: Db):
    meter = locked_meter(db, member, meter_id)
    row = scoped(db, MeterReading, household_id, reading_id, lock=True)
    if row.meter_id != meter.id:
        raise HTTPException(404, "Nie znaleziono odczytu tego licznika.")
    if row.updated_at != data.expected_updated_at:
        raise HTTPException(409, "Odczyt został zmieniony. Odśwież ekran.")
    audit(db, member, "meter.reading.deleted", row.id)
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/{meter_id}/photos", status_code=201)
def meter_photo(household_id: str, meter_id: str, member: Membership, db: Db, key: Key, file: UploadFile = File(...)):
    meter = scoped(db, Meter, household_id, meter_id)
    raw = file.file.read(MAX_IMAGE_BYTES + 1)
    try:
        image = validated_image(raw)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    digest = hashlib.sha256(image).hexdigest()
    lock = db.scalar(
        text("SELECT pg_try_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": f"meter-photo:{household_id}:{meter_id}:{key}"}
    )
    if not lock:
        raise HTTPException(409, "To zdjęcie jest już przetwarzane. Spróbuj za chwilę z tą samą operacją.")
    old = db.scalar(
        select(MeterPhoto).where(MeterPhoto.household_id == household_id, MeterPhoto.meter_id == meter_id, MeterPhoto.key == key)
    )
    if old:
        if old.image_hash != digest:
            raise HTTPException(409, "Ten zapis zdjęcia istnieje z inną zawartością.")
        return serialize(old)
    rate_limit(f"receipts:{member.user_id}", 12, 3600)
    rate_limit("receipt-service", 60, 3600)
    filename = "meter-" + secrets.token_hex(24) + ".png"
    destination = storage_path(filename)
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    committed = False
    created = False
    try:
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        created = True
        with os.fdopen(descriptor, "wb") as output:
            output.write(image)
        photo = MeterPhoto(
            household_id=household_id,
            meter_id=meter_id,
            path=filename,
            image_hash=digest,
            key=key,
            provider=settings.receipt_provider,
            model=settings.gemini_model
            if settings.receipt_provider == "gemini"
            else settings.openai_model
            if settings.receipt_provider == "openai"
            else "",
            created_by=member.user_id,
        )
        try:
            photo.proposal = extract_meter(image, meter.unit)
            photo.diagnostics = (
                {}
                if photo.proposal is not None
                else {"code": "AI_UNAVAILABLE", "message": "Zdjęcie zapisane. Wpisz stan ręcznie; odczyt AI jest niedostępny."}
            )
        except Exception as exc:
            photo.proposal = None
            photo.diagnostics = error_details(exc)
            photo.diagnostics["message"] = (
                "Odczyt licznika nie udał się. Zdjęcie zapisane — możesz wpisać stan ręcznie lub przesłać zdjęcie ponownie."
            )
        db.add(photo)
        db.commit()
        committed = True
        return serialize(photo)
    finally:
        if created and not committed:
            destination.unlink(missing_ok=True)


@router.get("/{meter_id}/photos/{photo_id}")
def photo_read(household_id: str, meter_id: str, photo_id: str, member: Membership, db: Db):
    scoped(db, Meter, household_id, meter_id)
    photo = scoped(db, MeterPhoto, household_id, photo_id)
    if photo.meter_id != meter_id:
        raise HTTPException(404, "Nie znaleziono zdjęcia.")
    path = storage_path(photo.path)
    if not path.is_file():
        raise HTTPException(404, "Zdjęcie jest niedostępne.")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "private, no-store"})
