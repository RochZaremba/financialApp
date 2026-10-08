from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app.domain import today
from app.main import app


def write(client, path, data, method="post", key=None):
    return client.request(method.upper(), path, json=data, headers={"Idempotency-Key": key or str(uuid4())})


def product(**overrides):
    return dict(name="Mleko", quantity=2000, unit="l", location="fridge", **overrides)


def stock(client, household, **overrides):
    data = dict(name="Mleko", quantity=2000, unit="l", location="fridge", minimum=0, expires_on=None)
    data.update(overrides)
    response = write(client, household["path"] + "/shopping/stock", data)
    assert response.status_code == 201, response.text
    return response.json()


def planned(client, household, **overrides):
    data = product()
    data.update(overrides)
    response = write(client, household["path"] + "/shopping/items", data)
    assert response.status_code == 201, response.text
    return response.json()


def purchase_body(row, **overrides):
    data = {
        "expected_updated_at": row["updated_at"],
        "purchased_on": today().isoformat(),
        "actual_amount": 579,
        "merchant": "Sklep",
        "add_to_stock": True,
    }
    data.update(overrides)
    return data


def test_purchase_is_atomic_idempotent_and_not_a_financial_expense(client, household):
    base = household["path"] + "/shopping"
    row = planned(client, household, estimated_amount=601)
    key = str(uuid4())
    body = purchase_body(row)
    first = write(client, f"{base}/items/{row['id']}/purchase", body, key=key)
    assert first.status_code == 200, first.text
    assert write(client, f"{base}/items/{row['id']}/purchase", body, key=key).json()["id"] == row["id"]
    assert write(client, f"{base}/items/{row['id']}/purchase", body).status_code == 409
    assert write(client, f"{base}/items/{row['id']}/purchase", {**body, "actual_amount": 580}, key=key).status_code == 409
    overview = client.get(base).json()
    assert overview["items"] == []
    assert len(overview["stock"]) == 1
    assert overview["stock"][0]["quantity"] == 2000
    history = client.get(base + "/history").json()
    assert history["total"] == 1
    assert history["items"][0]["actual_amount"] == 579
    assert client.get(household["path"] + "/transactions?month=2026-10").json()["items"] == []
    assert (
        write(client, f"{base}/items/{row['id']}", {**product(), "expected_updated_at": first.json()["updated_at"]}, "put").status_code
        == 409
    )


def test_exact_fractional_consumption_and_stale_changes(client, household):
    row = stock(client, household, quantity=300)
    path = household["path"] + f"/shopping/stock/{row['id']}"
    first_data = {"quantity": 100, "expected_updated_at": row["updated_at"]}
    key = str(uuid4())
    first = write(client, path + "/consume", first_data, key=key)
    assert first.status_code == 200, first.text
    assert first.json()["quantity"] == 200
    assert write(client, path + "/consume", first_data, key=key).json()["quantity"] == 200
    assert write(client, path + "/consume", first_data).status_code == 409
    second = write(client, path + "/consume", {"quantity": 100, "expected_updated_at": first.json()["updated_at"]})
    assert second.json()["quantity"] == 100
    assert write(client, path + "/consume", {"quantity": 101, "expected_updated_at": second.json()["updated_at"]}).status_code == 422
    assert client.get(household["path"] + "/shopping").json()["stock"][0]["quantity"] == 100


def test_concurrent_purchase_does_not_replenish_twice(client, household):
    row = planned(client, household)
    path = household["path"] + f"/shopping/items/{row['id']}/purchase"
    cookies = dict(client.cookies)

    def confirm(_):
        with TestClient(app) as other:
            other.cookies.update(cookies)
            return write(other, path, purchase_body(row)).status_code

    with ThreadPoolExecutor(max_workers=2) as workers:
        assert sorted(workers.map(confirm, range(2))) == [200, 409]
    assert len(client.get(household["path"] + "/shopping").json()["stock"]) == 1


def test_edit_and_delete_pending_products_keep_exact_totals(client, household):
    base = household["path"] + "/shopping"
    row = planned(client, household, estimated_amount=12345)
    planned(client, household, name="Chleb", quantity=1500, unit="szt")
    result = client.get(base).json()
    assert result["estimated_total"] == 12345 and result["unpriced_count"] == 1
    data = {**product(), "name": "Mleko zmienione", "estimated_amount": 9876, "expected_updated_at": row["updated_at"]}
    edited = write(client, base + f"/items/{row['id']}", data, "put")
    assert edited.status_code == 200, edited.text
    assert write(client, base + f"/items/{row['id']}", data, "put").status_code == 409
    assert client.get(base).json()["estimated_total"] == 9876
    key = str(uuid4())
    revision = {"expected_updated_at": edited.json()["updated_at"]}
    assert write(client, base + f"/items/{row['id']}", revision, "delete", key).status_code == 200
    assert write(client, base + f"/items/{row['id']}", revision, "delete", key).json() == {"ok": True}
    assert client.get(base).json()["estimated_total"] == 0


def test_low_stock_suggestions_aggregate_batches_exclude_expired_and_queued(client, household):
    stock(client, household, quantity=1000, minimum=5000)
    stock(client, household, quantity=500, minimum=0)
    stock(client, household, quantity=9000, expires_on=(today() - timedelta(days=1)).isoformat())
    result = client.get(household["path"] + "/shopping").json()
    assert result["suggestions"] == [dict(name="Mleko", quantity=3500, unit="l", location="fridge")]
    assert result["expiring_count"] == 1
    planned(client, household, name=" mleko ")
    assert client.get(household["path"] + "/shopping").json()["suggestions"] == []


def test_purchase_without_inventory_unknown_price_and_future_date(client, household):
    row = planned(client, household)
    path = household["path"] + f"/shopping/items/{row['id']}/purchase"
    assert write(client, path, purchase_body(row, purchased_on=(today() + timedelta(days=1)).isoformat())).status_code == 422
    result = write(client, path, purchase_body(row, add_to_stock=False, actual_amount=None))
    assert result.status_code == 200, result.text
    assert result.json()["inventory_id"] is None
    assert result.json()["actual_amount"] is None
    assert client.get(household["path"] + "/shopping").json()["stock"] == []


def test_history_search_is_bounded_and_literal(client, household):
    base = household["path"] + "/shopping"
    for name in ["Mleko", "Sok 100%", "Chleb"]:
        row = planned(client, household, name=name)
        assert write(client, f"{base}/items/{row['id']}/purchase", purchase_body(row)).status_code == 200
    assert client.get(base + "/history?q=%25").json()["total"] == 1
    assert client.get(base + "/history?q=sklep").json()["total"] == 3
    page = client.get(base + "/history?limit=1&offset=1").json()
    assert page["total"] == 3 and len(page["items"]) == 1
    assert client.get(base + "/history?limit=101").status_code == 422
    assert client.get(base + "/history?date_from=2026-10-09&date_to=2026-10-01").status_code == 422


def test_invalid_precision_units_and_blank_names_are_rejected(client, household):
    path = household["path"] + "/shopping/items"
    for change in [
        {"quantity": 0},
        {"quantity": 0.1},
        {"quantity": True},
        {"quantity": 1_000_000_001},
        {"unit": "tons"},
        {"estimated_amount": 1.2},
        {"estimated_amount": -1},
        {"name": "   "},
    ]:
        assert write(client, path, {**product(), **change}).status_code == 422


def test_second_member_shares_lists_but_another_household_cannot_access(client, household):
    row = planned(client, household)
    invite = client.post(household["path"] + "/invitations").json()
    with TestClient(app) as second:
        assert (
            second.post(
                "/auth/register", json={"name": "Kaja", "email": "kaja@example.com", "password": "another-long-password"}
            ).status_code
            == 201
        )
        join = second.post("/households/join", json={"token": invite["token"]})
        assert join.status_code == 200, join.text
        assert second.get(household["path"] + "/shopping").json()["items"][0]["id"] == row["id"]
        own = write(second, "/households", {"name": "Inny dom"}).json()
        own_path = f"/households/{own['id']}/shopping"
        assert write(second, own_path + f"/items/{row['id']}/purchase", purchase_body(row)).status_code == 404
        assert write(second, own_path + "/items", {**product(), "category_id": household["data"]["categories"][0]["id"]}).status_code == 404
    with TestClient(app) as outsider:
        outsider.post("/auth/register", json={"name": "Obcy", "email": "outsider@example.com", "password": "another-long-password"})
        assert outsider.get(household["path"] + "/shopping").status_code == 403
        assert outsider.get(household["path"] + "/shopping/history").status_code == 403
        assert outsider.get(household["path"] + "/shopping/receipts").status_code == 403
        assert write(outsider, household["path"] + "/shopping/items", product()).status_code == 403


def test_export_delete_preserves_purchase_snapshot_when_stock_removed(client, household):
    row = planned(client, household)
    purchased = write(client, household["path"] + f"/shopping/items/{row['id']}/purchase", purchase_body(row)).json()
    inventory = client.get(household["path"] + "/shopping").json()["stock"][0]
    assert (
        write(
            client, household["path"] + f"/shopping/stock/{inventory['id']}", {"expected_updated_at": inventory["updated_at"]}, "delete"
        ).status_code
        == 200
    )
    exported = client.get(household["path"] + "/export").json()
    assert len(exported["shopping_items"]) == 1
    assert exported["shopping_items"][0]["quantity"] == purchased["quantity"]
    assert exported["shopping_items"][0]["inventory_id"] is None
    assert exported["inventory_quantity_unit"] == "1/1000 of declared unit"
    assert client.request("DELETE", household["path"], json={"name": "Testowy dom"}).status_code == 200


def test_receipt_inventory_import_requires_confirmation_and_is_replay_safe(client, household):
    from test_product import upload, finalize

    base = household["path"] + "/shopping"
    receipt = upload(client, household).json()
    item = next(row for row in receipt["items"] if row["amount"] > 0)
    path = base + f"/receipt-items/{item['id']}"
    body = dict(name=item["name"], quantity=1250, unit="kg", location="fridge", expires_on=None)
    assert write(client, path, body).status_code == 422
    finalized = client.post(household["path"] + f"/receipts/{receipt['id']}/finalize", json=finalize(household, receipt))
    assert finalized.status_code == 200, finalized.text
    item = client.get(base + "/receipts").json()[0]["items"][0]
    path = base + f"/receipt-items/{item['id']}"
    body["name"] = item["name"]
    key = str(uuid4())
    result = write(client, path, body, key=key)
    assert result.status_code == 201, result.text
    assert write(client, path, body, key=key).json()["id"] == result.json()["id"]
    assert write(client, path, body).status_code == 409
    assert len(client.get(base).json()["stock"]) == 1
    assert client.get(base + "/history").json()["items"][0]["receipt_item_id"] == item["id"]
    choices = client.get(base + "/receipts").json()
    assert next(row for row in choices[0]["items"] if row["id"] == item["id"])["imported"] is True
    transactions = client.get(household["path"] + "/transactions?month=2026-10").json()["items"]
    assert len(transactions) == 1 and transactions[0]["amount"] == receipt["total"]
    assert client.request("DELETE", household["path"], json={"name": "Testowy dom"}).status_code == 200


def test_concurrent_stock_consumption_rejects_stale_revision(client, household):
    row = stock(client, household, quantity=1500)
    path = household["path"] + f"/shopping/stock/{row['id']}/consume"
    cookies = dict(client.cookies)

    def consume(_):
        with TestClient(app) as other:
            other.cookies.update(cookies)
            return write(other, path, {"quantity": 1000, "expected_updated_at": row["updated_at"]}).status_code

    with ThreadPoolExecutor(max_workers=2) as workers:
        assert sorted(workers.map(consume, range(2))) == [200, 409]
    assert client.get(household["path"] + "/shopping").json()["stock"][0]["quantity"] == 500


def test_receipt_can_complete_reviewed_pending_item_and_reject_stale_link(client, household):
    from test_product import upload, finalize

    receipt = upload(client, household).json()
    assert client.post(household["path"] + f"/receipts/{receipt['id']}/finalize", json=finalize(household, receipt)).status_code == 200
    base = household["path"] + "/shopping"
    line = client.get(base + "/receipts").json()[0]["items"][0]
    row = planned(client, household, name=line["name"])
    body = dict(name=line["name"], quantity=1500, unit="szt", location="pantry", shopping_item_id=row["id"])
    path = base + f"/receipt-items/{line['id']}"
    assert write(client, path, body).status_code == 409
    assert client.get(base).json()["stock"] == []
    result = write(client, path, {**body, "shopping_updated_at": row["updated_at"]})
    assert result.status_code == 201, result.text
    assert result.json()["id"] == row["id"]
    assert result.json()["quantity"] == 1500
    assert client.get(base).json()["items"] == []
    assert client.get(base + "/history").json()["total"] == 1
