import io
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pytest
import httpx
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from app.config import WARSAW, settings
from app.db import SessionLocal, engine
from app.domain import classify, month_dates, normalize
from app.main import app
from app.models import ClassificationRule, TransactionAllocation

ROOT = Path(__file__).resolve().parents[3]


def tx(home, **overrides):
    payload = {
        "kind": "expense",
        "amount": 13975,
        "date": "2026-10-04",
        "description": "Zakupy",
        "account_id": home["data"]["accounts"][0]["id"],
        "allocations": [{"category_id": home["data"]["categories"][0]["id"], "amount": 13975}],
    }
    payload.update(overrides)
    return payload


def post_tx(client, home, payload=None, key="test-key-123"):
    return client.post(home["path"] + "/transactions", json=payload or tx(home), headers={"Idempotency-Key": key})


def upload(client, home):
    return client.post(home["path"] + "/receipts", files={"file": ("lidl.png", (ROOT / "fixtures/lidl.png").read_bytes(), "image/png")})


@pytest.mark.parametrize("http_status", [200, 429])
def test_gemini_receipt_upload_and_failure_recovery(client, household, monkeypatch, http_status):
    monkeypatch.setattr(settings, "receipt_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", "private-test-key")
    expected = json.loads((ROOT / "fixtures/lidl.json").read_text())
    for item in expected["items"]:
        item["category_id"] = next((c["id"] for c in household["data"]["categories"] if c["name"] == item["category_id"]), None)
    payload = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(expected)}]}}]}
    monkeypatch.setattr(
        "app.receipts.httpx.post",
        lambda url, **kwargs: httpx.Response(http_status, json=payload, request=httpx.Request("POST", url)),
    )
    metadata = client.get("/auth/me")
    assert metadata.json()["receipt_provider"] == "gemini" and metadata.json()["receipt_ai_available"]
    assert "private-test-key" not in metadata.text
    receipt = upload(client, household).json()
    assert receipt["provider"] == "gemini"
    assert client.get(household["path"] + "/receipts/" + receipt["id"] + "/image").status_code == 200
    if http_status == 200:
        assert receipt["status"] == "ready" and receipt["total"] == 13975 and len(receipt["items"]) == 6
    else:
        assert receipt["status"] == "failed" and receipt["total"] is None and not receipt["items"]
        expected.update(merchant="Uzupełniony ręcznie")
        receipt.update(expected)
        for item in receipt["items"]:
            item["reviewed"] = False
    result = client.post(household["path"] + "/receipts/" + receipt["id"] + "/finalize", json=finalize(household, receipt))
    assert result.status_code == 200
    assert sum(a["amount"] for a in result.json()["allocations"]) == 13975
    overview = client.get(household["path"] + "/overview?month=2026-10").json()
    assert not overview["tasks"]


def finalize(home, receipt):
    items = [{k: i[k] for k in ["name", "quantity", "amount", "category_id", "confidence", "reviewed"]} for i in receipt["items"]]
    for item in items:
        if not item["category_id"]:
            item["category_id"] = next(c["id"] for c in home["data"]["categories"] if c["name"] == "Dom i zakupy")
            item["reviewed"] = True
    return {
        "merchant": receipt["merchant"],
        "date": receipt["date"],
        "total": receipt["total"],
        "account_id": home["data"]["accounts"][0]["id"],
        "items": items,
    }


def test_auth_sessions_and_invitation(client, household):
    invitation = client.post(household["path"] + "/invitations").json()
    second = TestClient(app)
    assert (
        second.post("/auth/register", json={"name": "Kaja", "email": "kaja@example.com", "password": "second-password-long"}).status_code
        == 201
    )
    assert second.post("/households/join", json={"token": invitation["token"]}).status_code == 200
    assert second.get(household["path"] + "/overview?month=2026-10").status_code == 200
    assert second.post("/households/join", json={"token": invitation["token"]}).status_code == 422
    assert second.post(household["path"] + "/invitations").status_code == 403
    saved = client.cookies.get("dom_session")
    assert client.post("/auth/logout").status_code == 200
    assert client.get("/auth/me").status_code == 401
    client.cookies.set("dom_session", saved)
    assert client.get("/auth/me").status_code == 401
    login = client.post("/auth/login", json={"email": "roch@example.com", "password": "a-long-test-password"})
    assert login.status_code == 200
    assert "HttpOnly" in login.headers["set-cookie"] and "SameSite=strict" in login.headers["set-cookie"]


def test_cross_household_authorization_every_route(client, household):
    receipt = upload(client, household).json()
    expense = post_tx(client, household).json()
    second = TestClient(app)
    second.post("/auth/register", json={"name": "Other", "email": "other@example.com", "password": "unrelated-password"})
    other = second.post("/households", json={"name": "Other home"}, headers={"Idempotency-Key": "other-home-key"}).json()
    prefix = household["path"]
    paths = [
        prefix + "/overview?month=2026-10",
        prefix + "/budget/2026-10",
        prefix + "/transactions",
        prefix + "/transactions/" + expense["id"],
        prefix + "/receipts/" + receipt["id"],
        prefix + "/receipts/" + receipt["id"] + "/image",
        prefix + "/analytics?month=2026-10",
        prefix + "/export",
    ]
    for path in paths:
        assert second.get(path).status_code == 403, path
    assert second.post(prefix + "/transactions", json=tx(household), headers={"Idempotency-Key": "unauthorized-key"}).status_code == 403
    assert second.request("DELETE", prefix, json={"name": "Testowy dom"}).status_code == 403
    other_data = second.get(f"/households/{other['id']}/overview?month=2026-10").json()
    bad = tx(household, account_id=other_data["accounts"][0]["id"])
    assert post_tx(client, household, bad, key="different-household-key-" + bad.get("account_id", "category")).status_code == 404
    bad = tx(household, allocations=[{"category_id": other_data["categories"][0]["id"], "amount": 13975}])
    assert post_tx(client, household, bad, key="different-household-key-" + bad.get("account_id", "category")).status_code == 404
    assert second.post(f"/households/{other['id']}/receipts/{receipt['id']}/finalize", json=finalize(household, receipt)).status_code == 404


def test_money_integer_and_allocation_balance(client, household):
    assert post_tx(client, household, tx(household, amount=139.75)).status_code == 422
    assert post_tx(client, household, tx(household, amount=True)).status_code == 422
    assert post_tx(client, household, tx(household, amount=0)).status_code == 422
    assert (
        post_tx(
            client, household, tx(household, allocations=[{"category_id": household["data"]["categories"][0]["id"], "amount": 100}])
        ).status_code
        == 422
    )
    assert post_tx(client, household).status_code == 201
    assert client.get(household["path"] + "/budget/2026-10").json()["expenses"] == 13975


def test_postgres_deferred_constraint_prevents_unbalanced_expense(client, household):
    created = post_tx(client, household).json()
    with engine.begin() as conn:
        assert conn.execute(text("SELECT amount FROM transactions WHERE id=:id"), {"id": created["id"]}).scalar() == 13975
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text("UPDATE transaction_allocations SET amount=amount-1 WHERE transaction_id=:id"), {"id": created["id"]})
    with SessionLocal() as db:
        assert db.scalar(select(TransactionAllocation.amount).where(TransactionAllocation.transaction_id == created["id"])) == 13975


def test_duplicate_manual_submit_and_concurrent_submit(client, household):
    first = post_tx(client, household).json()
    second = post_tx(client, household).json()
    assert first["id"] == second["id"]
    assert post_tx(client, household, tx(household, description="Changed")).status_code == 409
    cookies = dict(client.cookies)

    def submit(_):
        with TestClient(app) as parallel:
            parallel.cookies.update(cookies)
            return post_tx(parallel, household, key="concurrent-key-123")

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(submit, range(4)))
    assert all(r.status_code == 201 for r in results)
    assert len({r.json()["id"] for r in results}) == 1
    assert client.get(household["path"] + "/budget/2026-10").json()["expenses"] == 27950


def test_budget_zero_based_and_historical_snapshots(client, household):
    category = household["data"]["categories"][0]
    member = household["data"]["members"][0]
    payload = {
        "planned_income": 1000000,
        "allocations": [
            {"kind": "category", "reference_id": category["id"], "amount": 940000},
            {"kind": "pocket", "reference_id": member["id"], "amount": 60000},
        ],
    }
    assert client.put(household["path"] + "/budget/2026-10", json=payload).json()["unassigned"] == 0
    assert (
        client.patch(
            household["path"] + "/categories/" + category["id"],
            json={"name": "Nowa nazwa", "group": "Na co dzień", "icon": "house", "color": "green"},
        ).status_code
        == 200
    )
    old = client.get(household["path"] + "/budget/2026-10").json()
    assert old["allocations"][0]["label"] == category["name"] and old["allocations"][0]["group"] == "Potrzeby"
    assert client.put(household["path"] + "/budget/2026-11", json=payload).json()["allocations"][0]["label"] == "Nowa nazwa"
    assert client.get(household["path"] + "/budget/2026-10").json()["planned_income"] == 1000000
    assert client.put(household["path"] + "/budget/2026-13", json=payload).status_code == 422
    assert client.put(household["path"] + "/budget/2026-10", json={**payload, "allocations": payload["allocations"] * 2}).status_code == 422


def test_pocket_terminal_and_account_transfers(client, household):
    member = household["data"]["members"][0]
    accounts = household["data"]["accounts"]
    result = post_tx(client, household, tx(household, kind="pocket", amount=60000, member_id=member["id"], allocations=[])).json()
    assert result["kind"] == "pocket" and result["allocations"] == []
    b = client.get(household["path"] + "/budget/2026-10").json()
    assert b["pocket"] == 60000 and b["expenses"] == 0 and b["spent"] == 60000
    assert not client.get(household["path"] + "/overview?month=2026-10").json()["tasks"]
    transfer = tx(household, kind="transfer", amount=20000, destination_id=accounts[1]["id"], allocations=[])
    assert post_tx(client, household, transfer, "transfer-key").status_code == 201
    overview = client.get(household["path"] + "/overview?month=2026-10").json()
    assert sum(a["balance"] for a in overview["accounts"]) == -60000
    assert all(type(a["balance"]) is int for a in overview["accounts"])
    assert overview["budget"]["spent"] == 60000
    assert post_tx(client, household, tx(household, kind="pocket", allocations=[]), "bad-pocket-key").status_code == 422
    assert (
        post_tx(
            client, household, tx(household, kind="transfer", destination_id=accounts[0]["id"], allocations=[]), "bad-transfer-key"
        ).status_code
        == 422
    )


def test_receipt_fixture_ambiguous_review_and_learning(client, household):
    response = upload(client, household)
    assert response.status_code == 201
    receipt = response.json()
    assert receipt["total"] == 13975 and len(receipt["items"]) == 6
    tasks = client.get(household["path"] + "/overview?month=2026-10").json()["tasks"]
    assert len(tasks) == 1 and tasks[0]["kind"] == "classification"
    payload = finalize(household, receipt)
    not_reviewed = {**payload, "items": [{**i, "reviewed": False} for i in payload["items"]]}
    assert client.post(household["path"] + "/receipts/" + receipt["id"] + "/finalize", json=not_reviewed).status_code == 422
    bad = {**payload, "total": 13976}
    assert client.post(household["path"] + "/receipts/" + receipt["id"] + "/finalize", json=bad).status_code == 422
    path = household["path"] + "/receipts/" + receipt["id"] + "/finalize"
    first = client.post(path, json=payload)
    assert first.status_code == 200, first.text
    again = client.post(path, json=payload)
    assert again.json()["id"] == first.json()["id"]
    assert sum(a["amount"] for a in first.json()["allocations"]) == 13975 and len(first.json()["allocations"]) == 3
    assert not client.get(household["path"] + "/overview?month=2026-10").json()["tasks"]
    new = upload(client, household).json()
    assert new["items"][-1]["confidence"] == 100
    duplicate = client.post(household["path"] + "/receipts/" + new["id"] + "/finalize", json=finalize(household, new))
    assert duplicate.status_code == 409
    assert client.get(household["path"] + "/budget/2026-10").json()["expenses"] == 13975


def test_rule_priority_and_household_isolation(client, household):
    cat = household["data"]["categories"]
    home = household["id"]
    with SessionLocal() as db:
        db.add(ClassificationRule(household_id=home, pattern="Desperados", kind="exact", category_id=cat[0]["id"]))
        db.add(ClassificationRule(household_id=home, pattern="desperados", kind="normalized", category_id=cat[1]["id"]))
        db.add(ClassificationRule(household_id=home, pattern="lidl", kind="merchant", category_id=cat[2]["id"]))
        db.commit()
        assert classify(db, home, "Desperados", "Lidl") == (cat[0]["id"], 100)
        assert classify(db, home, "DESPERADOS", "Lidl") == (cat[1]["id"], 100)
        assert classify(db, home, "Inny produkt", "LIDL") == (cat[2]["id"], 100)
        assert classify(db, "unrelated-home", "Desperados", "Lidl") == (None, 0)
    assert normalize("  Żółty   CHLEB ") == "zolty chleb"


def test_unallocated_expense_inbox_resolution(client, household):
    response = post_tx(client, household, tx(household, allocations=[]))
    assert response.status_code == 201
    overview = client.get(household["path"] + "/overview?month=2026-10").json()
    assert len(overview["tasks"]) == 1
    assert overview["budget"]["spent"] == 13975 and overview["budget"]["unallocated"] == 13975
    result = client.put(household["path"] + "/transactions/" + response.json()["id"] + "/allocations", json=tx(household)["allocations"])
    assert result.status_code == 200
    assert not client.get(household["path"] + "/overview?month=2026-10").json()["tasks"]


def test_upload_private_validation_and_honest_unknown_photo(client, household):
    assert client.post(household["path"] + "/receipts", files={"file": ("fake.png", b"not an image", "image/png")}).status_code == 422
    assert (
        client.post(household["path"] + "/receipts", files={"file": ("big.png", b"x" * (10 * 1024 * 1024 + 1), "image/png")}).status_code
        == 413
    )
    im = Image.new("RGB", (80, 80), "white")
    buffer = io.BytesIO()
    im.save(buffer, "PNG")
    receipt = client.post(household["path"] + "/receipts", files={"file": ("real.png", buffer.getvalue(), "image/png")}).json()
    assert receipt["status"] == "draft" and receipt["total"] is None and receipt["items"] == []
    assert receipt["provider"] == "manual"
    image_path = household["path"] + "/receipts/" + receipt["id"] + "/image"
    assert client.get(image_path).status_code == 200
    assert TestClient(app).get(image_path).status_code == 401
    assert client.delete(household["path"] + "/receipts/" + receipt["id"]).status_code == 200
    assert client.get(image_path).status_code == 404


def test_category_archival_preserves_financial_history(client, household):
    expense = post_tx(client, household).json()
    category = household["data"]["categories"][0]["id"]
    assert client.delete(household["path"] + "/categories/" + category).status_code == 200
    assert client.get(household["path"] + "/transactions/" + expense["id"]).json()["allocations"][0]["category_id"] == category
    assert client.get(household["path"] + "/budget/2026-10").json()["expenses"] == 13975
    assert post_tx(client, household, key="new-archived-key").status_code == 422


def test_recurring_short_month_idempotence_and_disable(client, household):
    row = client.post(
        household["path"] + "/recurring",
        headers={"Idempotency-Key": "recurring-create-key"},
        json={
            "name": "Internet",
            "amount": 6900,
            "day": 31,
            "category_id": household["data"]["categories"][0]["id"],
            "account_id": household["data"]["accounts"][0]["id"],
        },
    ).json()
    path = household["path"] + "/recurring/" + row["id"] + "/pay/2028-02"
    first = client.post(path).json()
    again = client.post(path).json()
    assert first["id"] == again["id"] and first["date"] == "2028-02-29"
    assert client.get(household["path"] + "/budget/2028-02").json()["spent"] == 6900
    changed = client.put(
        household["path"] + "/recurring/" + row["id"],
        json={k: row[k] for k in ["name", "amount", "day", "category_id", "account_id"]} | {"active": False},
    )
    assert changed.status_code == 200
    assert client.post(household["path"] + "/recurring/" + row["id"] + "/pay/2028-03").status_code == 422


def test_goals_actual_contributions_and_analytics(client, household):
    goal = client.post(
        household["path"] + "/goals",
        headers={"Idempotency-Key": "goal-create-key"},
        json={"name": "Wakacje", "target": 800000, "opening_amount": 100000, "monthly_amount": 60000},
    ).json()
    accounts = household["data"]["accounts"]
    saving = tx(household, kind="saving", amount=60000, goal_id=goal["id"], destination_id=accounts[1]["id"], allocations=[])
    assert post_tx(client, household, saving).status_code == 201
    data = client.get(household["path"] + "/overview?month=2026-10").json()
    assert data["goals"][0]["current"] == 160000
    assert type(data["goals"][0]["current"]) is int
    assert data["goals"][0]["estimated_date"] is not None
    assert data["budget"]["savings"] == 60000 and data["budget"]["expenses"] == 0
    assert sum(a["balance"] for a in data["accounts"]) == 0
    assert client.get(household["path"] + "/analytics?month=2026-10").json()["savings_rate"] is None
    post_tx(client, household, tx(household, kind="income", amount=1000000, allocations=[]), "income-test-key")
    assert client.get(household["path"] + "/analytics?month=2026-10").json()["savings_rate"] == 6


def test_warsaw_month_boundaries():
    assert datetime(2026, 3, 31, 22, 30, tzinfo=timezone.utc).astimezone(WARSAW).date().isoformat() == "2026-04-01"
    assert month_dates("2028-02")[1].day == 29
    assert month_dates("2026-02")[1].day == 28


def test_security_csrf_rate_limits_and_export_delete(client, household):
    assert client.post("/auth/logout", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/auth/logout", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert client.get(household["path"] + "/export").json()["money_unit"] == "grosz"
    assert client.request("DELETE", household["path"], json={"name": "wrong"}).status_code == 422
    assert client.request("DELETE", household["path"], json={"name": "Testowy dom"}).status_code == 200
    assert client.get(household["path"] + "/overview?month=2026-10").status_code == 403
    assert client.get("/auth/me").status_code == 200
    for _ in range(15):
        client.post("/auth/login", json={"email": "bad@example.com", "password": "wrong-password-long"})
    assert client.post("/auth/login", json={"email": "bad@example.com", "password": "wrong-password-long"}).status_code == 429


def test_bounded_history_filters(client, household):
    post_tx(client, household)
    assert client.get(household["path"] + "/transactions?limit=101").status_code == 422
    assert client.get(household["path"] + "/transactions?offset=-1").status_code == 422
    assert client.get(household["path"] + "/transactions?month=2026-11").json()["items"] == []
    assert client.get(household["path"] + "/transactions?search=Zakupy&kind=expense&limit=1").json()["items"][0]["amount"] == 13975


def test_idempotency_for_household_and_other_financial_creation(client, household):
    payload = {"name": "Second home"}
    first = client.post("/households", json=payload, headers={"Idempotency-Key": "same-home-key"})
    again = client.post("/households", json=payload, headers={"Idempotency-Key": "same-home-key"})
    assert first.status_code == 201 and first.json()["id"] == again.json()["id"]
    for route, payload in [
        ("/accounts", {"name": "Nowe konto", "opening_balance": 20000}),
        ("/goals", {"name": "Nowy cel", "target": 100000}),
        ("/categories", {"name": "Nowa kategoria"}),
        (
            "/recurring",
            {
                "name": "Czynsz",
                "amount": 50000,
                "day": 2,
                "category_id": household["data"]["categories"][0]["id"],
                "account_id": household["data"]["accounts"][0]["id"],
            },
        ),
    ]:
        headers = {"Idempotency-Key": "same-create-key-" + route}
        one = client.post(household["path"] + route, json=payload, headers=headers)
        two = client.post(household["path"] + route, json=payload, headers=headers)
        assert one.status_code == 201, one.text
        assert one.json()["id"] == two.json()["id"]
        changed = client.post(household["path"] + route, json=payload | {"name": "Different name"}, headers=headers)
        assert changed.status_code == 409


def test_active_recurring_prevents_archiving_its_category(client, household):
    category = household["data"]["categories"][0]["id"]
    row = client.post(
        household["path"] + "/recurring",
        headers={"Idempotency-Key": "recurring-protection-key"},
        json={"name": "Czynsz", "amount": 200000, "day": 2, "category_id": category, "account_id": household["data"]["accounts"][0]["id"]},
    ).json()
    assert client.delete(household["path"] + "/categories/" + category).status_code == 409
    assert (
        client.put(
            household["path"] + "/recurring/" + row["id"],
            json={k: row[k] for k in ["name", "amount", "day", "category_id", "account_id"]} | {"active": False},
        ).status_code
        == 200
    )
    assert client.delete(household["path"] + "/categories/" + category).status_code == 200
    assert (
        client.put(
            household["path"] + "/recurring/" + row["id"],
            json={k: row[k] for k in ["name", "amount", "day", "category_id", "account_id"]} | {"active": True},
        ).status_code
        == 422
    )


def test_provider_failure_retains_private_photo_and_review_task(client, household, monkeypatch):
    class FailedProvider:
        def extract(self, image, categories):
            raise RuntimeError("external provider unavailable")

    monkeypatch.setattr("app.main.provider", lambda: FailedProvider())
    receipt = upload(client, household).json()
    assert receipt["status"] == "failed" and receipt["items"] == []
    assert client.get(household["path"] + "/receipts/" + receipt["id"] + "/image").status_code == 200
    tasks = client.get(household["path"] + "/overview?month=2026-10").json()["tasks"]
    assert tasks[0]["kind"] == "extraction"
    assert client.get(household["path"] + "/budget/2026-10").json()["spent"] == 0


def test_archived_actual_envelope_can_be_preserved_as_zero_plan(client, household):
    post_tx(client, household)
    category = household["data"]["categories"][0]["id"]
    assert client.delete(household["path"] + "/categories/" + category).status_code == 200
    payload = {"planned_income": 100000, "allocations": [{"kind": "category", "reference_id": category, "amount": 0}]}
    assert client.put(household["path"] + "/budget/2026-10", json=payload).status_code == 200
    assert client.get(household["path"] + "/budget/2026-10").json()["expenses"] == 13975
    payload["allocations"][0]["amount"] = 100
    assert client.put(household["path"] + "/budget/2026-11", json=payload).status_code == 422
    assert client.get(household["path"] + "/analytics?month=2000-01").status_code == 200


def test_expired_session_cannot_read_household(client, household):
    with engine.begin() as conn:
        conn.execute(text("UPDATE sessions SET expires_at=now()-interval '1 second'"))
    assert client.get("/auth/me").status_code == 401
    assert client.get(household["path"] + "/overview?month=2026-10").status_code == 401


def test_confident_receipt_remains_discoverable_until_finalization(client, household, monkeypatch):
    from app.schemas import Extraction, ExtractedItem

    class ConfidentProvider:
        def extract(self, image, categories):
            return Extraction(
                merchant="Pewny sklep",
                date="2026-10-05",
                total=1234,
                items=[ExtractedItem(name="Jabłka", quantity="1", amount=1234, category_id=categories[0]["id"], confidence=99)],
            )

    monkeypatch.setattr("app.main.provider", lambda: ConfidentProvider())
    receipt = upload(client, household).json()
    assert receipt["status"] == "ready"
    overview = client.get(household["path"] + "/overview?month=2026-10").json()
    assert overview["tasks"][0]["kind"] == "confirmation" and overview["tasks"][0]["receipt_id"] == receipt["id"]
    assert overview["budget"]["spent"] == 0
    assert client.post(household["path"] + "/receipts/" + receipt["id"] + "/finalize", json=finalize(household, receipt)).status_code == 200
    assert not client.get(household["path"] + "/overview?month=2026-10").json()["tasks"]
