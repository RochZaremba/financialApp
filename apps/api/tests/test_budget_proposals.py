import json
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.planning import Proposal, ProposedCategory, ai_proposal, divide_money


def request(home, mode="history"):
    categories = home["data"]["categories"]
    return dict(
        mode=mode,
        preferences="Więcej na dom",
        draft=dict(
            planned_income=100001,
            allocations=[dict(kind="category", reference_id=c["id"], amount=0) for c in categories]
            + [dict(kind="pocket", reference_id=home["data"]["members"][0]["id"], amount=20000)],
        ),
    )


def test_exact_distribution_every_category_preserves_commitments_and_draft(client, household):
    url = household["path"] + "/budget/2026-10/proposal"
    response = client.post(url, json=request(household))
    assert response.status_code == 200
    proposal = response.json()
    assert sum(r["amount"] for r in proposal["allocations"]) == 80001
    assert proposal["reserved"] == 20000 and proposal["mode"] == "history"
    assert {r["category_id"] for r in proposal["allocations"]} == {c["id"] for c in household["data"]["categories"]}
    assert not client.get(household["path"] + "/budget/2026-10").json()["period"]
    assert not client.get(household["path"] + "/transactions").json()["items"]
    assert divide_money(10001, [50, 30, 20]) == [5001, 3000, 2000]


def test_history_is_household_scoped_and_recurring_floor_is_visible(client, household):
    data = household["data"]
    categories = data["categories"]
    client.post(
        household["path"] + "/transactions",
        json=dict(
            kind="expense",
            amount=10000,
            date="2026-09-01",
            description="Dom",
            account_id=data["accounts"][0]["id"],
            allocations=[dict(category_id=categories[1]["id"], amount=10000)],
        ),
        headers={"Idempotency-Key": str(uuid4())},
    )
    client.post(
        household["path"] + "/recurring",
        json=dict(name="Czynsz", day=1, amount=30000, category_id=categories[0]["id"], account_id=data["accounts"][0]["id"]),
        headers={"Idempotency-Key": str(uuid4())},
    )
    result = client.post(household["path"] + "/budget/2026-10/proposal", json=request(household)).json()
    amounts = {r["category_id"]: r["amount"] for r in result["allocations"]}
    assert amounts[categories[0]["id"]] == 30000 and amounts[categories[1]["id"]] == 50001
    outsider = TestClient(app)
    outsider.post("/auth/register", json=dict(email="proposal-outsider@example.com", password="private-proposal-password"))
    assert outsider.post(household["path"] + "/budget/2026-10/proposal", json=request(household)).status_code == 403


def test_unavailable_invalid_ids_and_overcommitted_budget(client, household, monkeypatch):
    monkeypatch.setattr(settings, "budget_ai_provider", "history")
    url = household["path"] + "/budget/2026-10/proposal"
    assert client.post(url, json=request(household, "ai")).status_code == 503
    data = request(household)
    data["draft"]["planned_income"] = 19999
    assert client.post(url, json=data).status_code == 422
    data = request(household)
    data["draft"]["allocations"][0]["reference_id"] = str(uuid4())
    assert client.post(url, json=data).status_code == 404


@pytest.mark.parametrize("defect", ["wrong_total", "foreign_category", "duplicate", "below_recurring"])
def test_model_output_is_never_trusted_or_saved(client, household, monkeypatch, defect):
    rows = [ProposedCategory(category_id=c["id"], amount=0, reason="Propozycja") for c in household["data"]["categories"]]
    rows[0].amount = 80001
    if defect == "wrong_total":
        rows[0].amount = 80000
    elif defect == "foreign_category":
        rows[0].category_id = str(uuid4())
    elif defect == "below_recurring":
        rows[0].amount = 0
        rows[1].amount = 80001
        client.post(
            household["path"] + "/recurring",
            json=dict(
                name="Czynsz", day=1, amount=30000, category_id=rows[0].category_id, account_id=household["data"]["accounts"][0]["id"]
            ),
            headers={"Idempotency-Key": str(uuid4())},
        )
    else:
        rows.append(rows[0])
    monkeypatch.setattr("app.planning.ai_proposal", lambda _: Proposal(summary="AI", assumptions=["Sprawdź"], allocations=rows))
    assert client.post(household["path"] + "/budget/2026-10/proposal", json=request(household, "ai")).status_code == 502
    assert not client.get(household["path"] + "/budget/2026-10").json()["period"]


@pytest.mark.parametrize("provider", ["openai", "gemini"])
def test_real_provider_protocol_uses_strict_json_and_aggregate_context(monkeypatch, provider):
    monkeypatch.setattr(settings, "budget_ai_provider", provider)
    monkeypatch.setattr(settings, provider + "_api_key", "test-only-key")
    output = dict(
        summary="Propozycja", assumptions=["Niepewna historia"], allocations=[dict(category_id="cat", amount=123, reason="Historia")]
    )
    calls = []

    def send(url, **kwargs):
        calls.append((url, kwargs))
        if provider == "openai":
            body = dict(status="completed", output=[dict(content=[dict(type="output_text", text=json.dumps(output))])])
        else:
            body = dict(candidates=[dict(finishReason="STOP", content=dict(parts=[dict(text=json.dumps(output))]))])
        return httpx.Response(200, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr("app.planning.httpx.post", send)
    assert ai_proposal(dict(category_pool=123, categories=[dict(id="cat", name="Dom")])).allocations[0].amount == 123
    payload = calls[0][1]["json"]
    if provider == "openai":
        assert payload["store"] is False and payload["text"]["format"]["strict"] is True
    else:
        assert payload["generationConfig"]["responseFormat"]["text"]["mimeType"] == "APPLICATION_JSON"
    assert "receipt" not in json.dumps(payload).lower()


@pytest.mark.parametrize(
    "provider,body",
    [("openai", []), ("openai", {"status": "incomplete"}), ("gemini", []), ("gemini", {"candidates": [{"finishReason": "SAFETY"}]})],
)
def test_malformed_or_incomplete_provider_envelope_is_recoverable(monkeypatch, provider, body):
    from fastapi import HTTPException

    monkeypatch.setattr(settings, "budget_ai_provider", provider)
    monkeypatch.setattr(settings, provider + "_api_key", "test-only-key")
    monkeypatch.setattr("app.planning.httpx.post", lambda url, **kwargs: httpx.Response(200, json=body, request=httpx.Request("POST", url)))
    with pytest.raises(HTTPException) as error:
        ai_proposal(dict(category_pool=0, categories=[]))
    assert error.value.status_code == 502


@pytest.mark.parametrize("carried,scheduled,new_income", [(50000, 50000, 0), (20000, 30000, 10000)])
def test_carried_envelope_funds_recurring_without_allocating_income_twice(client, household, carried, scheduled, new_income):
    path = household["path"]
    category = household["data"]["categories"][0]["id"]
    account = household["data"]["accounts"][0]["id"]
    assert (
        client.put(
            path + "/budget/2026-09",
            json=dict(planned_income=carried, allocations=[dict(kind="category", reference_id=category, amount=carried)]),
        ).status_code
        == 200
    )
    assert (
        client.post(
            path + "/transactions",
            json=dict(kind="income", amount=carried, date="2026-09-01", description="Wpływ", account_id=account),
            headers={"Idempotency-Key": str(uuid4())},
        ).status_code
        == 201
    )
    carry = dict(mode="carry", envelopes=[dict(category_id=category, amount=carried)])
    preview = client.post(path + "/budget/2026-09/settlement-preview", json=carry)
    assert preview.status_code == 200
    assert (
        client.post(path + "/budget/2026-09/settle", json=dict(**carry, preview_token=preview.json()["preview_token"])).status_code == 200
    )
    assert (
        client.post(
            path + "/recurring",
            json=dict(name="Czynsz", day=1, amount=scheduled, category_id=category, account_id=account),
            headers={"Idempotency-Key": str(uuid4())},
        ).status_code
        == 201
    )
    before = client.get(path + "/budget/2026-10").json()
    draft = request(household)
    draft["draft"]["planned_income"] = new_income
    draft["draft"]["allocations"] = [a for a in draft["draft"]["allocations"] if a["kind"] == "category"]
    response = client.post(path + "/budget/2026-10/proposal", json=draft)
    assert response.status_code == 200
    result = response.json()
    assert sum(a["amount"] for a in result["allocations"]) == new_income
    assert next(a["amount"] for a in result["allocations"] if a["category_id"] == category) == new_income
    assert not any("nie pokrywa" in text for text in result["assumptions"])
    assert client.get(path + "/budget/2026-10").json() == before
    assert before["available"] == carried and before["income"] == 0 and before["planned_income"] == 0
