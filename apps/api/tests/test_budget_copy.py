from fastapi.testclient import TestClient
from app.main import app


def test_copy_preview_preserves_sources_and_never_books_money(client, household):
    path = household["path"]
    data = household["data"]
    original = {
        "income_sources": [{"name": "Wynagrodzenie", "member_id": data["members"][0]["id"], "amount": 123456}],
        "allocations": [
            {"kind": "category", "reference_id": data["categories"][0]["id"], "amount": 23456},
            {"kind": "pocket", "reference_id": data["members"][0]["id"], "amount": 100000},
        ],
    }
    assert client.put(path + "/budget/2026-10", json=original).status_code == 200
    before = client.get(path + "/budget/2026-10").json()
    preview = client.get(path + "/budget/2026-11/copy-preview?source_month=2026-10")
    assert preview.status_code == 200
    draft = preview.json()
    assert draft["planned_income"] == 123456 and draft["allocations"][0]["amount"] == 23456
    assert draft["income_sources"] == original["income_sources"]
    assert client.get(path + "/budget/2026-11").json()["period"] is None
    saved = client.put(
        path + "/budget/2026-11",
        json={
            "income_sources": draft["income_sources"],
            "allocations": [{k: a[k] for k in ["kind", "reference_id", "amount"]} for a in draft["allocations"]],
            "expected_updated_at": None,
        },
    )
    assert saved.status_code == 200 and saved.json()["unassigned"] == 0 and saved.json()["income"] == 0
    assert client.get(path + "/budget/2026-10").json() == before
    assert not client.get(path + "/transactions").json()["items"]


def test_copy_omits_archived_entries_and_enforces_household(client, household):
    path = household["path"]
    category = household["data"]["categories"][0]["id"]
    assert (
        client.put(
            path + "/budget/2026-10",
            json={"planned_income": 10001, "allocations": [{"kind": "category", "reference_id": category, "amount": 10001}]},
        ).status_code
        == 200
    )
    assert client.delete(path + "/categories/" + category).status_code == 200
    preview = client.get(path + "/budget/2026-11/copy-preview?source_month=2026-10").json()
    assert not preview["allocations"] and preview["omitted"] == [household["data"]["categories"][0]["name"]]
    assert client.get(path + "/budget/2026-10/copy-preview?source_month=2026-10").status_code == 422
    assert client.get(path + "/budget/2026-11/copy-preview?source_month=2026-09").status_code == 404
    assert client.get(path + "/budget/2026-11/copy-preview?source_month=2026-13").status_code == 422
    other = TestClient(app)
    assert other.post("/auth/register", json={"email": "copy-other@example.com", "password": "private-password-long"}).status_code == 201
    assert other.get(path + "/budget/2026-11/copy-preview?source_month=2026-10").status_code == 403


def test_budget_editor_revision_prevents_lost_copy(client, household):
    path = household["path"] + "/budget/2026-10"
    initial = client.put(path, json={"planned_income": 10001, "allocations": [], "expected_updated_at": None}).json()
    assert (
        client.put(
            path, json={"planned_income": 20002, "allocations": [], "expected_updated_at": initial["period"]["updated_at"]}
        ).status_code
        == 200
    )
    assert (
        client.put(
            path, json={"planned_income": 30003, "allocations": [], "expected_updated_at": initial["period"]["updated_at"]}
        ).status_code
        == 409
    )
    assert client.put(path, json={"planned_income": 40004, "allocations": [], "expected_updated_at": None}).status_code == 409
    assert client.get(path).json()["planned_income"] == 20002
