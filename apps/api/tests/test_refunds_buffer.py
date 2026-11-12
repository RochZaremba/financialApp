from datetime import timedelta
from uuid import uuid4

from app.domain import today


def create_tx(client, home, kind, amount, category=None, *, day=None, account=None):
    payload = dict(
        kind=kind,
        amount=amount,
        date=(day or today()).isoformat(),
        description="CALZEDONIA",
        account_id=account or home["data"]["accounts"][0]["id"],
    )
    if category:
        payload["allocations"] = [{"category_id": category, "amount": amount}]
    response = client.post(home["path"] + "/transactions", json=payload, headers={"Idempotency-Key": uuid4().hex})
    assert response.status_code == 201, response.text
    return response.json()


def refund(client, home, original, amount, *, key=None, day=None):
    data = dict(
        amount=amount,
        date=(day or today()).isoformat(),
        account_id=original["account_id"],
        description="Zwrot CALZEDONIA",
        expected_updated_at=original["updated_at"],
    )
    return client.post(
        home["path"] + "/transactions/" + original["id"] + "/refund", json=data, headers={"Idempotency-Key": key or uuid4().hex}
    )


def overview(client, home):
    response = client.get(home["path"] + "/overview?month=" + today().strftime("%Y-%m"))
    assert response.status_code == 200, response.text
    return response.json()


def test_partial_refunds_are_net_spending_and_cash_without_income_and_retries(client, household):
    category = household["data"]["categories"][0]["id"]
    original = create_tx(client, household, "expense", 24999, category)
    key = uuid4().hex
    response = refund(client, household, original, 10000, key=key)
    assert response.status_code == 201, response.text
    assert refund(client, household, original, 10000, key=key).json()["id"] == response.json()["id"]
    assert response.json()["is_refund"] and response.json()["refund_of_id"] == original["id"]
    data = overview(client, household)
    assert data["budget"]["income"] == 0 and data["budget"]["expenses"] == 14999 and data["budget"]["refunds"] == 10000
    assert data["accounts"][0]["balance"] == -14999
    assert next(a for a in data["budget"]["allocations"] if a["reference_id"] == category)["spent"] == 14999
    assert client.get(household["path"] + "/transactions?kind=income").json()["items"] == []
    assert len(client.get(household["path"] + "/transactions?kind=refund").json()["items"]) == 1
    original = client.get(household["path"] + "/transactions/" + original["id"]).json()
    assert original["refundable_amount"] == 14999
    assert refund(client, household, original, 15000).status_code == 422
    assert refund(client, household, original, 14999).status_code == 201
    assert overview(client, household)["budget"]["expenses"] == 0
    assert overview(client, household)["accounts"][0]["balance"] == 0


def test_uncategorized_original_refunds_inherit_later_categories(client, household):
    original = create_tx(client, household, "expense", 1000)
    r = refund(client, household, original, 300)
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "unallocated"
    assert overview(client, household)["budget"]["unallocated"] == 700
    category = household["data"]["categories"][0]["id"]
    response = client.put(
        household["path"] + "/transactions/" + original["id"] + "/allocations", json=[{"category_id": category, "amount": 1000}]
    )
    assert response.status_code == 200, response.text
    result = client.get(household["path"] + "/transactions/" + r.json()["id"]).json()
    assert result["status"] == "categorized" and result["allocations"][0]["amount"] == 300
    assert overview(client, household)["budget"]["unallocated"] == 0


def test_refund_caps_dates_revision_and_household_references(client, household):
    original = create_tx(client, household, "expense", 1000)
    assert refund(client, household, original, 100, day=today() - timedelta(days=1)).status_code == 422
    assert refund(client, household, original, 1001).status_code == 422
    assert refund(client, household, original, 100).status_code == 201
    assert refund(client, household, original, 100).status_code == 409
    stranger = client.post("/households", json={"name": "Obcy dom"}, headers={"Idempotency-Key": uuid4().hex}).json()
    body = dict(
        amount=100,
        date=today().isoformat(),
        account_id=original["account_id"],
        description="Zwrot",
        expected_updated_at=original["updated_at"],
    )
    assert (
        client.post(
            "/households/" + stranger["id"] + "/transactions/" + original["id"] + "/refund",
            json=body,
            headers={"Idempotency-Key": uuid4().hex},
        ).status_code
        == 404
    )


def plan_with_buffer(client, home, income, amounts):
    response = client.post(
        home["path"] + "/categories", json={"name": "Bufor", "group": "Potrzeby"}, headers={"Idempotency-Key": uuid4().hex}
    )
    assert response.status_code == 201, response.text
    buffer_id = response.json()["id"]
    allocations = [{"kind": "category", "reference_id": cat, "amount": amount} for cat, amount in amounts.items()]
    allocations.append({"kind": "category", "reference_id": buffer_id, "amount": 0})
    response = client.put(
        home["path"] + "/budget/" + today().strftime("%Y-%m"),
        json={"planned_income": income, "buffer_category_id": buffer_id, "allocations": allocations},
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert response.status_code == 200, response.text
    return buffer_id, response.json()


def test_buffer_automatically_gets_remainder_covers_and_refund_releases_it(client, household):
    food, home = [r["id"] for r in household["data"]["categories"][:2]]
    buffer_id, plan = plan_with_buffer(client, household, 100000, {food: 20000, home: 40000})
    assert plan["buffer"]["planned"] == 40000 and plan["unassigned"] == 0
    original = create_tx(client, household, "expense", 25000, food)
    create_tx(client, household, "expense", 45000, home)
    budget = overview(client, household)["budget"]
    assert budget["buffer"]["covered"] == 10000 and budget["buffer"]["remaining"] == 30000
    assert {r["reference_id"]: r["covered"] for r in budget["buffer"]["recipients"]} == {food: 5000, home: 5000}
    assert budget["spent"] == 70000 and budget["remaining"] == 30000
    assert refund(client, household, original, 10000).status_code == 201
    budget = overview(client, household)["budget"]
    assert budget["buffer"]["covered"] == 5000 and budget["buffer"]["remaining"] == 35000
    assert budget["expenses"] == 60000 and budget["remaining"] == 40000
    assert sum(a["remaining"] for a in budget["allocations"]) == budget["remaining"]
    assert next(a for a in budget["allocations"] if a["reference_id"] == buffer_id)["amount"] == 40000


def test_insufficient_buffer_never_creates_money_and_keeps_overruns_visible(client, household):
    food, home = [r["id"] for r in household["data"]["categories"][:2]]
    _, _ = plan_with_buffer(client, household, 10000, {food: 4000, home: 4000})
    create_tx(client, household, "expense", 7000, food)
    create_tx(client, household, "expense", 5000, home)
    budget = overview(client, household)["budget"]
    assert budget["buffer"]["covered"] == 2000 and budget["buffer"]["uncovered"] == 2000 and budget["buffer"]["remaining"] == 0
    assert {r["reference_id"]: r["covered"] for r in budget["buffer"]["recipients"]} == {food: 1500, home: 500}
    assert budget["remaining"] == -2000 and sum(a["remaining"] for a in budget["allocations"]) == -2000


def test_partial_refund_rounding_preserves_every_original_category_grosz(client, household):
    food, home = [c["id"] for c in household["data"]["categories"][:2]]
    account = household["data"]["accounts"][0]["id"]
    original = client.post(
        household["path"] + "/transactions",
        json={
            "kind": "expense",
            "amount": 3,
            "date": today().isoformat(),
            "account_id": account,
            "description": "Mieszany zakup",
            "allocations": [{"category_id": food, "amount": 2}, {"category_id": home, "amount": 1}],
        },
        headers={"Idempotency-Key": uuid4().hex},
    ).json()
    first = refund(client, household, original, 1)
    assert first.status_code == 201, first.text
    assert {a["category_id"]: a["amount"] for a in first.json()["allocations"]} == {food: 1}
    original = client.get(household["path"] + "/transactions/" + original["id"]).json()
    second = refund(client, household, original, 2)
    assert second.status_code == 201, second.text
    assert {a["category_id"]: a["amount"] for a in second.json()["allocations"]} == {food: 1, home: 1}
    assert overview(client, household)["budget"]["expenses"] == 0
    assert all(a["spent"] == 0 for a in overview(client, household)["budget"]["allocations"])


def test_changing_original_categories_updates_refund_without_changing_cash(client, household):
    food, home = [c["id"] for c in household["data"]["categories"][:2]]
    original = create_tx(client, household, "expense", 1000, food)
    returned = refund(client, household, original, 300).json()
    result = client.put(
        household["path"] + "/transactions/" + original["id"] + "/allocations", json=[{"category_id": home, "amount": 1000}]
    )
    assert result.status_code == 200, result.text
    returned = client.get(household["path"] + "/transactions/" + returned["id"]).json()
    assert {a["category_id"]: a["amount"] for a in returned["allocations"]} == {home: 300}
    data = overview(client, household)
    assert data["accounts"][0]["balance"] == -700 and data["budget"]["expenses"] == 700


def test_refunded_original_financial_values_are_protected_but_notes_editable(client, household):
    original = create_tx(client, household, "expense", 1000, household["data"]["categories"][0]["id"])
    r = refund(client, household, original, 200).json()
    original = client.get(household["path"] + "/transactions/" + original["id"]).json()
    base = {k: original[k] for k in ("kind", "date", "description", "account_id", "destination_id", "member_id", "goal_id")}
    base["allocations"] = [{"category_id": a["category_id"], "amount": a["amount"]} for a in original["allocations"]]
    base["expected_updated_at"] = original["updated_at"]
    base["amount"] = 1000
    bad = {**base, "amount": 900, "allocations": [{"category_id": base["allocations"][0]["category_id"], "amount": 900}]}
    assert (
        client.put(household["path"] + "/transactions/" + original["id"], json=bad, headers={"Idempotency-Key": uuid4().hex}).status_code
        == 422
    )
    edit = {k: r[k] for k in ("kind", "amount", "date", "account_id", "destination_id", "member_id", "goal_id")}
    edit.update(description="Poprawiony opis zwrotu", allocations=[], expected_updated_at=r["updated_at"])
    result = client.put(household["path"] + "/transactions/" + r["id"], json=edit, headers={"Idempotency-Key": uuid4().hex})
    assert result.status_code == 200, result.text
    assert result.json()["allocations"][0]["amount"] == 200 and result.json()["is_refund"]


def test_manual_refund_correction_recalculates_cash_categories_and_retains_cap(client, household):
    original = create_tx(client, household, "expense", 1000, household["data"]["categories"][0]["id"])
    returned = refund(client, household, original, 200).json()
    edit = {k: returned[k] for k in ("kind", "date", "account_id", "destination_id", "member_id", "goal_id")}
    edit.update(amount=400, description="Poprawiona kwota zwrotu", allocations=[], expected_updated_at=returned["updated_at"])
    path = household["path"] + "/transactions/" + returned["id"]
    key = {"Idempotency-Key": uuid4().hex}
    response = client.put(path, json=edit, headers=key)
    assert response.status_code == 200, response.text
    assert response.json()["allocations"][0]["amount"] == 400
    assert client.put(path, json=edit, headers=key).json()["id"] == returned["id"]
    data = overview(client, household)
    assert data["budget"]["expenses"] == 600 and data["budget"]["income"] == 0
    assert data["accounts"][0]["balance"] == -600
    edit.update(amount=1001, expected_updated_at=response.json()["updated_at"])
    assert client.put(path, json=edit, headers={"Idempotency-Key": uuid4().hex}).status_code == 422
    edit.update(amount=400, date=(today() - timedelta(days=1)).isoformat())
    assert client.put(path, json=edit, headers={"Idempotency-Key": uuid4().hex}).status_code == 422
    assert overview(client, household)["accounts"][0]["balance"] == -600


def test_deferred_database_guards_refund_limit_and_household(client, household):
    import pytest
    from sqlalchemy.exc import IntegrityError
    from app.db import SessionLocal
    from app.models import Transaction

    original = create_tx(client, household, "expense", 1000)
    stranger = client.post("/households", json={"name": "Drugi dom"}, headers={"Idempotency-Key": uuid4().hex}).json()
    for amount, home in [(1001, household["id"]), (100, stranger["id"])]:
        with SessionLocal() as db:
            db.add(
                Transaction(
                    household_id=home,
                    kind="income",
                    amount=amount,
                    date=today(),
                    description="Niepoprawny zwrot",
                    account_id=original["account_id"],
                    status="unallocated",
                    source="manual",
                    refund_of_id=original["id"],
                    idempotency_key=uuid4().hex,
                    request_hash="a" * 64,
                )
            )
            with pytest.raises(IntegrityError):
                db.commit()
            db.rollback()
    assert overview(client, household)["budget"]["refunds"] == 0


def test_buffer_disable_is_preserved_by_older_clients_and_copy_keeps_selection(client, household):
    category = household["data"]["categories"][0]["id"]
    buffer_id, plan = plan_with_buffer(client, household, 10000, {category: 4000})
    month = today().strftime("%Y-%m")
    target = "2027-01" if month != "2027-01" else "2027-02"
    preview = client.get(household["path"] + "/budget/" + target + "/copy-preview?source_month=" + month).json()
    assert preview["buffer_category_id"] == buffer_id
    allocations = [
        {"kind": "category", "reference_id": category, "amount": 4000},
        {"kind": "category", "reference_id": buffer_id, "amount": 6000},
    ]
    result = client.put(
        household["path"] + "/budget/" + month, json={"planned_income": 10000, "buffer_category_id": None, "allocations": allocations}
    )
    assert result.status_code == 200, result.text
    assert result.json()["buffer"] is None and result.json()["buffer_category_id"] is None
    result = client.put(household["path"] + "/budget/" + month, json={"planned_income": 10000, "allocations": allocations})
    assert result.status_code == 200 and result.json()["buffer"] is None
