from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import Member, Receipt, Transaction

ROOT = Path(__file__).resolve().parents[3]


def join(person, household, name="Kaja"):
    result = person.post("/auth/register", json={"name": name, "email": f"{uuid4().hex}@example.com", "password": "activity-test-password"})
    assert result.status_code == 201
    identifier = result.json()["id"]
    with SessionLocal() as db:
        db.add(Member(household_id=household["id"], user_id=identifier))
        db.commit()
    return identifier


def movement(client, home, kind="expense", amount=101, key=None, **overrides):
    data = dict(
        kind=kind,
        amount=amount,
        date="2026-10-04",
        description="Wpis aktywności",
        account_id=home["data"]["accounts"][0]["id"],
        allocations=[dict(category_id=home["data"]["categories"][0]["id"], amount=amount)] if kind == "expense" else [],
    )
    data.update(overrides)
    response = client.post(home["path"] + "/transactions", json=data, headers={"Idempotency-Key": key or uuid4().hex})
    assert response.status_code == 201, response.text
    return response.json(), data


def upload(client, home, key=None):
    result = client.post(
        home["path"] + "/receipts",
        files={"file": ("lidl.png", (ROOT / "fixtures/lidl.png").read_bytes(), "image/png")},
        headers={"Idempotency-Key": key or uuid4().hex},
    )
    assert result.status_code == 201, result.text
    return result.json()


def test_activity_is_household_private(client, household):
    with TestClient(app) as other:
        assert other.get(household["path"] + "/activity").status_code == 401
        other.post("/auth/register", json={"email": "other@example.com", "password": "other-activity-password"})
        assert other.get(household["path"] + "/activity").status_code == 403
    for month in ("bad", "1999-12", "2026-13", ""):
        assert client.get(household["path"] + "/activity", params={"month": month}).status_code == 422


def test_two_people_exact_totals_zero_members_and_no_transfer_counts(client, household):
    owner = client.get("/auth/me").json()["user"]["id"]
    movement(client, household, amount=100_000_000_000)
    movement(client, household, amount=101)
    upload(client, household)
    with TestClient(app) as second, TestClient(app) as inactive:
        kaja = join(second, household)
        zero = join(inactive, household, "Bez wpisów")
        movement(second, household, kind="income", amount=2_000_000_003)
        movement(second, household, kind="transfer", amount=42, destination_id=household["data"]["accounts"][1]["id"])
        data = second.get(household["path"] + "/activity").json()
    assert data["totals"] == dict(receipts=1, expenses=2, expense_amount=100_000_000_101, incomes=1, income_amount=2_000_000_003)
    people = {row["user_id"]: row for row in data["people"]}
    assert people[owner]["expenses"] == 2 and people[owner]["receipts"] == 1
    assert people[kaja]["incomes"] == 1 and people[kaja]["name"] == "Kaja"
    assert people[zero]["expenses"] == people[zero]["receipts"] == people[zero]["incomes"] == 0
    assert "email" not in str(data) and "password" not in str(data)


def test_creation_month_uses_warsaw_boundaries_including_dst_not_transaction_date(client, household):
    beginning = datetime(2026, 9, 30, 22, tzinfo=timezone.utc)
    end = datetime(2026, 10, 31, 23, tzinfo=timezone.utc)
    dates = [beginning - timedelta(microseconds=1), beginning, end - timedelta(microseconds=1), end]
    for index, instant in enumerate(dates):
        tx, _ = movement(client, household, kind="income", amount=index + 101, date="2025-01-01")
        receipt = upload(client, household)
        with SessionLocal() as db:
            db.get(Transaction, tx["id"]).created_at = instant
            db.get(Receipt, receipt["id"]).created_at = instant
            db.commit()
    data = client.get(household["path"] + "/activity?month=2026-10").json()
    assert data["totals"]["incomes"] == data["totals"]["receipts"] == 2
    assert data["totals"]["income_amount"] == 102 + 103
    assert client.get(household["path"] + "/activity").json()["totals"]["incomes"] == 4


def test_legacy_and_former_authors_are_explicit_and_household_records_stay_separate(client, household):
    legacy, _ = movement(client, household)
    with SessionLocal() as db:
        db.get(Transaction, legacy["id"]).created_by = None
        db.commit()
    with TestClient(app) as second:
        former = join(second, household, "Dawny domownik")
        movement(second, household, kind="income", amount=321)
        with SessionLocal() as db:
            db.delete(db.scalar(select(Member).where(Member.household_id == household["id"], Member.user_id == former)))
            db.commit()
        foreign = second.post("/households", json={"name": "Inny dom"}, headers={"Idempotency-Key": uuid4().hex}).json()
        overview = second.get(f"/households/{foreign['id']}/overview?month=2026-10").json()
        movement(second, {"path": f"/households/{foreign['id']}", "data": overview}, kind="income", amount=999)
    data = client.get(household["path"] + "/activity").json()
    people = {row["user_id"]: row for row in data["people"]}
    assert people[None]["name"] == "Nieznany autor" and people[None]["expenses"] == 1
    assert people[former]["name"] == "Dawny domownik" and people[former]["current_member"] is False
    assert data["totals"]["income_amount"] == 321
    assert client.get(household["path"] + f"/transactions/{legacy['id']}").json()["created_by_name"] is None


def test_authenticated_author_cannot_be_spoofed_or_reassigned_by_edit_or_retry(client, household):
    owner = client.get("/auth/me").json()["user"]["id"]
    original, payload = movement(client, household, key="shared-activity-operation")
    assert original["created_by"] == owner and original["created_by_name"] == "Roch"
    assert (
        client.post(
            household["path"] + "/transactions", json=dict(payload, created_by="fake"), headers={"Idempotency-Key": uuid4().hex}
        ).status_code
        == 422
    )
    with TestClient(app) as second:
        join(second, household)
        replay = second.post(household["path"] + "/transactions", json=payload, headers={"Idempotency-Key": "shared-activity-operation"})
        assert replay.json()["created_by"] == owner
        edited = second.put(
            household["path"] + f"/transactions/{original['id']}",
            json=dict(payload, description="Poprawione przez drugą osobę", expected_updated_at=original["updated_at"]),
            headers={"Idempotency-Key": uuid4().hex},
        )
        assert edited.status_code == 200, edited.text
        assert edited.json()["created_by"] == owner and edited.json()["created_by_name"] == "Roch"
    data = client.get(household["path"] + "/activity").json()
    assert data["totals"]["expenses"] == 1
    assert client.get(household["path"] + "/transactions").json()["items"][0]["created_by_name"] == "Roch"
    assert client.get(household["path"] + "/overview?month=2026-10").json()["recent"][0]["created_by_name"] == "Roch"


def test_receipt_uploader_and_expense_confirmer_are_separate_and_idempotent(client, household):
    owner = client.get("/auth/me").json()["user"]["id"]
    receipt = upload(client, household, key="shared-receipt-operation")
    assert receipt["created_by_name"] == "Roch"
    with TestClient(app) as second:
        kaja = join(second, household)
        assert upload(second, household, key="shared-receipt-operation")["created_by"] == owner
        path = household["path"] + f"/receipts/{receipt['id']}"
        retry = second.post(path + "/ocr", headers={"Idempotency-Key": "second-person-reread"})
        assert retry.status_code == 200
        payload = dict(
            merchant="Wspólny paragon",
            date="2026-10-04",
            total=1001,
            items=[dict(name="Zakup", amount=1001, category_id=household["data"]["categories"][0]["id"], confidence=100, reviewed=True)],
        )
        assert second.put(path, json=payload).json()["created_by_name"] == "Roch"
        finalized = second.post(path + "/finalize", json=dict(payload, account_id=household["data"]["accounts"][0]["id"]))
        assert finalized.status_code == 200, finalized.text
        assert finalized.json()["created_by"] == kaja and finalized.json()["created_by_name"] == "Kaja"
        assert second.post(path + "/finalize", json=dict(payload, account_id=household["data"]["accounts"][0]["id"])).status_code == 200
        assert second.get(path).json()["created_by_name"] == "Roch"
    people = {row["user_id"]: row for row in client.get(household["path"] + "/activity").json()["people"]}
    assert people[owner]["receipts"] == 1 and people[owner]["expenses"] == 0
    assert people[kaja]["receipts"] == 0 and people[kaja]["expenses"] == 1 and people[kaja]["expense_amount"] == 1001
