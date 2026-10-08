from uuid import uuid4

from fastapi.testclient import TestClient
from app.main import app


def setup(client, home):
    data = home["data"]
    cats = data["categories"]
    client.put(
        home["path"] + "/budget/2026-09",
        json=dict(
            planned_income=100001,
            allocations=[
                dict(kind="category", reference_id=cats[0]["id"], amount=50001),
                dict(kind="category", reference_id=cats[1]["id"], amount=50000),
            ],
        ),
    )
    response = client.post(
        home["path"] + "/transactions",
        json=dict(
            kind="income", amount=100001, date="2026-09-01", description="Wpływ", account_id=data["accounts"][0]["id"], allocations=[]
        ),
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 201
    return dict(mode="carry", envelopes=[dict(category_id=cats[0]["id"], amount=50001), dict(category_id=cats[1]["id"], amount=50000)])


def test_carry_is_not_income_and_is_independent_after_plan_save(client, household):
    payload = setup(client, household)
    route = household["path"] + "/budget/2026-09"
    preview = client.post(route + "/settlement-preview", json=payload)
    assert preview.status_code == 200
    assert not client.get(household["path"] + "/budget/2026-10").json()["period"]
    confirmed = dict(**payload, preview_token=preview.json()["preview_token"])
    response = client.post(route + "/settle", json=confirmed)
    assert response.status_code == 200
    assert client.post(route + "/settle", json=confirmed).json() == response.json()
    target = client.get(household["path"] + "/budget/2026-10").json()
    assert target["carry_in"] == 100001 and target["income"] == 0 and target["planned_income"] == 0
    assert target["remaining"] == 100001 and target["unassigned"] == 0
    assert sum(a["remaining"] for a in target["allocations"]) == 100001
    assert client.put(household["path"] + "/budget/2026-10", json=dict(planned_income=30000, allocations=[])).status_code == 200
    target = client.get(household["path"] + "/budget/2026-10").json()
    assert target["remaining"] == 130001 and target["unassigned"] == 30000
    source = client.get(route).json()
    assert source["carry_out"] == 100001 and source["remaining"] == 0
    assert all(a["remaining"] == 0 for a in source["allocations"])
    assert len(client.get(household["path"] + "/transactions").json()["items"]) == 1
    assert client.get(household["path"] + "/export").json()["budget_settlements"]
    assert client.request("DELETE", household["path"], json=dict(name="Testowy dom")).status_code == 200


def test_distribution_rounding_accounts_goal_and_remembered_ratios(client, household):
    payload = setup(client, household)
    data = household["data"]
    accounts = []
    for name in ["Oszczędności", "Cel"]:
        accounts.append(
            client.post(
                household["path"] + "/accounts", json=dict(name=name, kind="savings"), headers={"Idempotency-Key": str(uuid4())}
            ).json()["id"]
        )
    goal = client.post(
        household["path"] + "/goals", json=dict(name="Wakacje", target=1000000), headers={"Idempotency-Key": str(uuid4())}
    ).json()["id"]
    payload.update(
        mode="distribute",
        account_id=data["accounts"][0]["id"],
        transfer_date="2026-10-08",
        targets=[dict(account_id=accounts[0], basis_points=7000), dict(account_id=accounts[1], goal_id=goal, basis_points=3000)],
    )
    route = household["path"] + "/budget/2026-09"
    preview = client.post(route + "/settlement-preview", json=payload)
    assert preview.status_code == 200
    assert [r["amount"] for r in preview.json()["targets"]] == [70001, 30000]
    confirm = dict(**payload, preview_token=preview.json()["preview_token"])
    assert client.post(route + "/settle", json=confirm).status_code == 422
    confirm["transfers_performed"] = True
    assert client.post(route + "/settle", json=confirm).status_code == 200
    assert client.post(route + "/settle", json=confirm).status_code == 200
    current = client.get(household["path"] + "/overview?month=2026-10").json()
    assert current["goals"][0]["current"] == 30000
    balances = {a["id"]: a["balance"] for a in current["accounts"]}
    assert balances[accounts[0]] == 70001 and balances[accounts[1]] == 30000
    assert current["budget"]["spent"] == 0 and current["budget"]["income"] == 0
    assert client.get(route).json()["savings"] == 100001
    assert client.get(route).json()["remaining"] == 0
    policy = client.get(household["path"] + "/surplus-policy").json()
    assert [r["basis_points"] for r in policy["targets"]] == [7000, 3000]
    transfers = client.get(household["path"] + "/transactions?month=2026-10").json()["items"]
    tx = transfers[0]
    edit = {key: tx[key] for key in ["kind", "amount", "date", "description", "account_id", "destination_id", "member_id", "goal_id"]}
    edit.update(expected_updated_at=tx["updated_at"], allocations=[])
    assert (
        client.put(household["path"] + "/transactions/" + tx["id"], json=edit, headers={"Idempotency-Key": str(uuid4())}).status_code == 409
    )


def test_stale_closed_source_and_invalid_funding_are_atomic(client, household):
    payload = setup(client, household)
    route = household["path"] + "/budget/2026-09"
    token = client.post(route + "/settlement-preview", json=payload).json()["preview_token"]
    assert client.put(route, json=dict(planned_income=99999, allocations=[])).status_code == 200
    assert client.post(route + "/settle", json=dict(**payload, preview_token=token)).status_code == 422
    payload = setup(client, household)
    token = client.post(route + "/settlement-preview", json=payload).json()["preview_token"]
    # An unrelated account balance change invalidates the captured preview.
    client.post(
        household["path"] + "/transactions",
        json=dict(kind="income", amount=1, date="2026-10-08", description="Wpływ", account_id=household["data"]["accounts"][0]["id"]),
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert client.post(route + "/settle", json=dict(**payload, preview_token=token)).status_code == 409
    token = client.post(route + "/settlement-preview", json=payload).json()["preview_token"]
    assert client.post(route + "/settle", json=dict(**payload, preview_token=token)).status_code == 200
    assert client.put(route, json=dict(planned_income=100001, allocations=[])).status_code == 409
    assert (
        client.post(
            household["path"] + "/transactions",
            json=dict(kind="income", amount=1, date="2026-09-01", description="Wpływ", account_id=household["data"]["accounts"][0]["id"]),
            headers={"Idempotency-Key": str(uuid4())},
        ).status_code
        == 409
    )
    outsider = TestClient(app)
    outsider.post("/auth/register", json=dict(email="surplus-outsider@example.com", password="private-surplus-password"))
    assert outsider.post(route + "/settlement-preview", json=payload).status_code == 403


def test_surplus_cannot_exceed_actual_funding_or_net_month_balance(client, household):
    payload = setup(client, household)
    route = household["path"] + "/budget/2026-09"
    account = household["data"]["accounts"][0]["id"]
    category = household["data"]["categories"][0]["id"]
    expense = client.post(
        household["path"] + "/transactions",
        json=dict(
            kind="expense",
            amount=70000,
            date="2026-09-02",
            description="Wydatek",
            account_id=account,
            allocations=[dict(category_id=category, amount=70000)],
        ),
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert expense.status_code == 201
    # Other envelope still has 500 PLN; only 300.01 PLN remains across the household.
    payload["envelopes"] = [payload["envelopes"][1]]
    assert client.post(route + "/settlement-preview", json=payload).status_code == 422
    payload["envelopes"][0]["amount"] = 30001
    assert client.post(route + "/settlement-preview", json=payload).status_code == 200
    tx = expense.json()
    token = client.post(route + "/settlement-preview", json=payload).json()["preview_token"]
    assert client.post(route + "/settle", json=dict(**payload, preview_token=token)).status_code == 200
    assert (
        client.put(
            household["path"] + "/transactions/" + tx["id"] + "/allocations",
            json=[dict(category_id=a["category_id"], amount=a["amount"]) for a in tx["allocations"]],
        ).status_code
        == 409
    )


def test_distribution_validates_ratios_destinations_and_source_balance(client, household):
    payload = setup(client, household)
    destination = client.post(
        household["path"] + "/accounts", json=dict(name="Rezerwa", kind="savings"), headers={"Idempotency-Key": str(uuid4())}
    ).json()["id"]
    payload.update(
        mode="distribute",
        account_id=household["data"]["accounts"][0]["id"],
        transfer_date="2026-10-08",
        targets=[dict(account_id=destination, basis_points=9999)],
    )
    route = household["path"] + "/budget/2026-09/settlement-preview"
    assert client.post(route, json=payload).status_code == 422
    payload["targets"][0]["basis_points"] = 10000
    payload["targets"][0]["account_id"] = str(uuid4())
    assert client.post(route, json=payload).status_code == 404
    payload["targets"][0]["account_id"] = destination
    payload["account_id"] = household["data"]["accounts"][1]["id"]
    assert client.post(route, json=payload).status_code == 422
    payload["account_id"] = household["data"]["accounts"][0]["id"]
    payload["transfer_date"] = "2026-11-01"
    assert client.post(route, json=payload).status_code == 422


def test_settlement_cannot_close_unpaid_pocket_money_or_goal_commitment(client, household):
    payload = setup(client, household)
    path = household["path"]
    category = household["data"]["categories"][0]["id"]
    member = household["data"]["members"][0]["id"]
    goal = client.post(path + "/goals", json=dict(name="Poduszka", target=1000000), headers={"Idempotency-Key": str(uuid4())}).json()["id"]
    for kind, reference in [("pocket", member), ("goal", goal)]:
        assert (
            client.put(
                path + "/budget/2026-09",
                json=dict(
                    planned_income=100001,
                    allocations=[
                        dict(kind="category", reference_id=category, amount=50001),
                        dict(kind=kind, reference_id=reference, amount=50000),
                    ],
                ),
            ).status_code
            == 200
        )
        payload["envelopes"] = [dict(category_id=category, amount=50001)]
        assert client.post(path + "/budget/2026-09/settlement-preview", json=payload).status_code == 422
