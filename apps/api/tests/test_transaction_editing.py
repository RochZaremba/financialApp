from uuid import uuid4

from fastapi.testclient import TestClient
from app.main import app
from test_product import tx, post_tx, upload, finalize


def edit(client, home, original, **changes):
    payload = {
        name: original.get(name)
        for name in ["kind", "amount", "date", "description", "account_id", "destination_id", "member_id", "goal_id"]
    }
    payload["allocations"] = [{k: a[k] for k in ["category_id", "amount"]} for a in original["allocations"]]
    payload["expected_updated_at"] = original["updated_at"]
    payload.update(changes)
    return client.put(home["path"] + "/transactions/" + original["id"], json=payload, headers={"Idempotency-Key": str(uuid4())})


def test_edit_updates_exact_balances_month_and_splits(client, household):
    original = post_tx(client, household).json()
    new = edit(
        client,
        household,
        original,
        amount=12301,
        date="2026-11-01",
        description="Poprawione zakupy",
        allocations=[{"category_id": household["data"]["categories"][1]["id"], "amount": 12301}],
    )
    assert new.status_code == 200
    assert new.json()["id"] == original["id"] and new.json()["updated_at"] != original["updated_at"]
    october = client.get(household["path"] + "/overview?month=2026-10").json()
    november = client.get(household["path"] + "/overview?month=2026-11").json()
    assert october["budget"]["expenses"] == 0 and november["budget"]["expenses"] == 12301
    account = next(a for a in november["accounts"] if a["id"] == original["account_id"])
    assert account["balance"] == account["opening_balance"] - 12301
    assert edit(client, household, original, description="Stale").status_code == 409
    assert client.get(household["path"] + "/transactions/" + original["id"]).json()["description"] == "Poprawione zakupy"


def test_edit_validation_and_idempotency(client, household):
    original = post_tx(client, household).json()
    assert edit(client, household, original, amount=10000).status_code == 422
    assert edit(client, household, original, kind="income", allocations=[]).status_code == 422
    assert edit(client, household, original, account_id="foreign").status_code == 404
    assert edit(client, household, original, date="1999-12-31").status_code == 422
    payload = {**tx(household), "description": "Idempotent edit", "expected_updated_at": original["updated_at"]}
    route = household["path"] + "/transactions/" + original["id"]
    headers = {"Idempotency-Key": "edit-retry-key"}
    first = client.put(route, json=payload, headers=headers)
    assert first.status_code == 200
    assert client.put(route, json=payload, headers=headers).json() == first.json()
    payload["amount"] += 1
    assert client.put(route, json=payload, headers=headers).status_code == 409
    # Replaying the original creation request must not revert the edit.
    assert post_tx(client, household).json()["description"] == "Idempotent edit"


def test_edit_inbox_and_household_authorization(client, household):
    original = post_tx(client, household).json()
    unallocated = edit(client, household, original, allocations=[]).json()
    assert unallocated["status"] == "unallocated"
    overview = client.get(household["path"] + "/overview?month=2026-10").json()
    assert len(overview["tasks"]) == 1
    revised = edit(client, household, unallocated, allocations=tx(household)["allocations"])
    assert revised.status_code == 200
    assert not client.get(household["path"] + "/overview?month=2026-10").json()["tasks"]
    outsider = TestClient(app)
    assert outsider.post("/auth/register", json={"email": "outside@example.com", "password": "long-private-password"}).status_code == 201
    assert edit(outsider, household, revised.json()).status_code == 403


def test_receipt_edit_preserves_documentary_evidence(client, household):
    receipt = upload(client, household).json()
    original = client.post(household["path"] + "/receipts/" + receipt["id"] + "/finalize", json=finalize(household, receipt)).json()
    assert edit(client, household, original, amount=original["amount"] + 1).status_code == 422
    assert edit(client, household, original, date="2026-10-08").status_code == 422
    changed = edit(client, household, original, description="Zakupy dla domu")
    assert changed.status_code == 200
    assert client.get(household["path"] + "/receipts/" + receipt["id"]).json()["total"] == original["amount"]


def test_edit_transfer_and_savings_keep_household_total(client, household):
    data = household["data"]
    goal = client.post(
        household["path"] + "/goals", json={"name": "Wakacje", "target": 200000}, headers={"Idempotency-Key": "goal-edit-test"}
    ).json()
    original = post_tx(
        client,
        household,
        tx(household, kind="saving", amount=10101, allocations=[], destination_id=data["accounts"][1]["id"], goal_id=goal["id"]),
    ).json()
    revised = edit(client, household, original, amount=20202)
    assert revised.status_code == 200
    overview = client.get(household["path"] + "/overview?month=2026-10").json()
    assert overview["goals"][0]["current"] == 20202
    assert sum(a["balance"] for a in overview["accounts"]) == sum(a["opening_balance"] for a in data["accounts"])
    assert overview["budget"]["savings"] == 20202
