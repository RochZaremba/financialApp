import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.db import SessionLocal
from app.models import Receipt, ReceiptItem
from app.schemas import Extraction
from app.security import _attempts
from test_product import finalize, upload

ROOT = Path(__file__).resolve().parents[3]


def test_password_whitespace_is_preserved_and_not_echoed(client):
    credentials = {"email": "spaces@example.com", "password": "  exact-password  "}
    assert client.post("/auth/register", json=credentials).status_code == 201
    assert client.post("/auth/logout").status_code == 200
    response = client.post("/auth/login", json={**credentials, "password": "exact-password"})
    assert response.status_code == 401 and "password" not in response.text
    assert client.post("/auth/login", json=credentials).status_code == 200


def test_partial_draft_retains_unknowns_and_cannot_finalize(client, household):
    receipt = upload(client, household).json()
    path = household["path"] + "/receipts/" + receipt["id"]
    payload = {"merchant": "Poprawiony sklep", "date": None, "total": None, "items": [{"name": "Tylko odczytana nazwa", "amount": None}]}
    saved = client.put(path, json=payload)
    assert saved.status_code == 200
    reloaded = client.get(path).json()
    assert reloaded["merchant"] == "Poprawiony sklep"
    assert reloaded["date"] is None and reloaded["total"] is None and reloaded["items"][0]["amount"] is None
    assert reloaded["error"] is None
    assert client.post(path + "/finalize", json={**payload, "account_id": household["data"]["accounts"][0]["id"]}).status_code == 422
    assert client.get(household["path"] + "/transactions").json()["items"] == []
    tasks = client.get(household["path"] + "/overview?month=2026-10").json()["tasks"]
    assert tasks[0]["title"] == "Poprawiony sklep" and tasks[0]["kind"] == "extraction"
    assert client.put(path, json={"merchant": "Only header", "items": []}).status_code == 200


def test_discounts_balance_categories_without_learning_generic_rule(client, household):
    receipt = upload(client, household).json()
    path = household["path"] + "/receipts/" + receipt["id"]
    category, other = [c["id"] for c in household["data"]["categories"][:2]]
    payload = {
        "merchant": "Sklep",
        "date": "2026-10-05",
        "total": 2001,
        "account_id": household["data"]["accounts"][0]["id"],
        "items": [
            {"name": "Zakup", "amount": 2002, "category_id": category, "reviewed": True},
            {"name": "Rabat", "amount": -1, "category_id": other, "reviewed": True},
        ],
    }
    assert client.post(path + "/finalize", json=payload).status_code == 422
    assert client.get(household["path"] + "/transactions").json()["items"] == []
    payload["items"][1]["category_id"] = category
    result = client.post(path + "/finalize", json=payload)
    assert result.status_code == 200 and result.json()["allocations"][0]["amount"] == 2001
    assert client.get(path).json()["items"][1]["amount"] == -1
    overview = client.get(household["path"] + "/overview?month=2026-10").json()
    assert overview["budget"]["expenses"] == 2001
    assert not any(r["pattern"] == "rabat" for r in overview["rules"])
    assert (
        Extraction.model_validate(
            {k: v for k, v in payload.items() if k != "account_id"}
            | {"items": [{"name": "Rabat", "quantity": "1", "amount": -1, "category_id": category, "confidence": 80}]}
        )
        .items[0]
        .amount
        == -1
    )


@pytest.mark.parametrize("failure", [False, True])
def test_concurrent_upload_retry_extracts_only_once(client, household, monkeypatch, failure):
    calls = []
    lock = Lock()
    from app.receipts import FixtureProvider

    original = FixtureProvider.extract

    def extract(self, image, categories):
        with lock:
            calls.append(1)
        if failure:
            raise ValueError("External provider failed")
        return original(self, image, categories)

    monkeypatch.setattr(FixtureProvider, "extract", extract)
    cookies = dict(client.cookies)
    path = household["path"] + "/receipts"
    key = {"Idempotency-Key": "same-upload-operation-123"}

    def submit(_):
        with TestClient(app) as parallel:
            parallel.cookies.update(cookies)
            return parallel.post(path, headers=key, files={"file": ("lidl.png", (ROOT / "fixtures/lidl.png").read_bytes(), "image/png")})

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(submit, range(3)))
    assert all(r.status_code == 201 for r in results)
    assert len({r.json()["id"] for r in results}) == 1 and len(calls) == 1
    assert len(_attempts[f"receipts:{household['data']['members'][0]['user_id']}"]) == 1
    with SessionLocal() as db:
        assert len(list(db.scalars(select(Receipt)))) == 1
        assert len(list(db.scalars(select(ReceiptItem)))) == (0 if failure else 6)
    changed = client.post(
        path, headers=key, files={"file": ("icon.png", (ROOT / "apps/web/public/icon-192.png").read_bytes(), "image/png")}
    )
    assert changed.status_code == 409


def test_concurrent_finalization_is_one_balanced_transaction(client, household):
    receipt = upload(client, household).json()
    payload = finalize(household, receipt)
    cookies = dict(client.cookies)

    def submit(_):
        with TestClient(app) as parallel:
            parallel.cookies.update(cookies)
            return parallel.post(household["path"] + "/receipts/" + receipt["id"] + "/finalize", json=payload)

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(submit, range(3)))
    assert all(r.status_code == 200 for r in results)
    assert len({r.json()["id"] for r in results}) == 1
    overview = client.get(household["path"] + "/overview?month=2026-10").json()
    assert overview["budget"]["expenses"] == 13975 and not overview["tasks"]


def test_streamed_body_limit_without_content_length(client):
    body = json.dumps({"email": "too-large@example.com", "password": "a" * (129 * 1024)}).encode()
    response = client.post("/auth/register", headers={"Content-Type": "application/json"}, content=iter([body[:65536], body[65536:]]))
    assert response.status_code == 413
    assert "content-length" not in response.request.headers


def test_monthly_budget_uses_bounded_query_count(client, household):
    from sqlalchemy import event
    from app.db import engine
    from test_product import post_tx, tx

    for index in range(40):
        assert (
            post_tx(
                client,
                household,
                tx(household, amount=1, allocations=[{"category_id": household["data"]["categories"][0]["id"], "amount": 1}]),
                key=f"load-query-key-{index}",
            ).status_code
            == 201
        )
    queries = []

    def count(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            queries.append(statement)

    event.listen(engine, "before_cursor_execute", count)
    try:
        result = client.get(household["path"] + "/budget/2026-10")
    finally:
        event.remove(engine, "before_cursor_execute", count)
    assert result.status_code == 200 and result.json()["expenses"] == 40
    assert result.json()["allocations"][0]["spent"] == 40
    assert len(queries) <= 10, f"Monthly budget used {len(queries)} queries for 40 expenses"


def test_long_receipt_classification_uses_bounded_query_count(client, household, monkeypatch):
    from sqlalchemy import event
    from app.db import engine
    from app.receipts import FixtureProvider

    category = household["data"]["categories"][0]["id"]
    extraction = Extraction(
        merchant="Duży koszyk",
        date="2026-10-05",
        total=200,
        items=[{"name": f"Pozycja {i}", "quantity": "1", "amount": 1, "category_id": category, "confidence": 95} for i in range(200)],
    )
    monkeypatch.setattr(FixtureProvider, "extract", lambda *args: extraction)
    queries = []

    def count(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            queries.append(statement)

    event.listen(engine, "before_cursor_execute", count)
    try:
        result = upload(client, household)
    finally:
        event.remove(engine, "before_cursor_execute", count)
    assert result.status_code == 201 and len(result.json()["items"]) == 200
    assert len(queries) <= 20, f"Receipt classification used {len(queries)} queries for 200 items"


def test_bad_logins_do_not_lock_other_accounts_behind_same_proxy(client, household):
    for _ in range(15):
        assert client.post("/auth/login", json={"email": "attacked@example.com", "password": "wrong-password-long"}).status_code == 401
    assert client.post("/auth/login", json={"email": "attacked@example.com", "password": "wrong-password-long"}).status_code == 429
    assert client.post("/auth/login", json={"email": "roch@example.com", "password": "a-long-test-password"}).status_code == 200


def test_streamed_multipart_body_limit_without_content_length(client, household):
    boundary = "release-body-limit"
    prefix = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="big.png"\r\nContent-Type: image/png\r\n\r\n'
    ).encode()

    def chunks():
        yield prefix
        for _ in range(172):
            yield b"x" * 65536
        yield f"\r\n--{boundary}--\r\n".encode()

    response = client.post(
        household["path"] + "/receipts", headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, content=chunks()
    )
    assert response.status_code == 413
    assert "content-length" not in response.request.headers


def test_compressed_image_pixel_limit_is_an_error(monkeypatch):
    import io
    from PIL import Image
    from app.receipts import validated_image

    image = io.BytesIO()
    Image.new("RGB", (11, 10), "white").save(image, format="PNG")
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 100)
    with pytest.raises(ValueError, match="Nie można odczytać"):
        validated_image(image.getvalue())


def test_sanitized_image_is_bounded_even_when_png_is_larger_than_input(monkeypatch):
    import io
    from PIL import Image
    from app import receipts

    # A compressed JPEG can expand when sanitized to PNG. Exercise that branch
    # with a small byte limit rather than allocating a giant test photo.
    raw = io.BytesIO()
    Image.effect_noise((100, 100), 100).convert("RGB").save(raw, format="JPEG", quality=40)
    monkeypatch.setattr(receipts, "MAX_IMAGE_BYTES", len(raw.getvalue()) + 100)
    sanitized = receipts.validated_image(raw.getvalue())
    assert len(sanitized) <= receipts.MAX_IMAGE_BYTES
    with Image.open(io.BytesIO(sanitized)) as result:
        assert result.format == "PNG" and result.width < 100


def test_confident_but_negative_category_net_requires_receipt_review(client, household, monkeypatch):
    from app.receipts import FixtureProvider

    category, other = [c["id"] for c in household["data"]["categories"][:2]]
    extraction = Extraction(
        merchant="Rabat w złej kategorii",
        date="2026-10-05",
        total=999,
        items=[
            {"name": "Zakup", "quantity": "1", "amount": 1000, "category_id": category, "confidence": 99},
            {"name": "Rabat", "quantity": "1", "amount": -1, "category_id": other, "confidence": 99},
        ],
    )
    monkeypatch.setattr(FixtureProvider, "extract", lambda *args: extraction)
    receipt = upload(client, household).json()
    assert receipt["status"] == "ready"
    tasks = client.get(household["path"] + "/overview?month=2026-10").json()["tasks"]
    assert tasks[0]["kind"] == "classification"
    assert client.post(household["path"] + "/receipts/" + receipt["id"] + "/finalize", json=finalize(household, receipt)).status_code == 422


def test_extracted_unread_price_retains_item_as_incomplete_draft(client, household, monkeypatch):
    from app.receipts import FixtureProvider

    category = household["data"]["categories"][0]["id"]
    extraction = Extraction(
        merchant="Częściowy odczyt",
        date="2026-10-05",
        total=100,
        items=[{"name": "Czytelna nazwa", "quantity": "1", "amount": None, "category_id": category, "confidence": 99}],
    )
    monkeypatch.setattr(FixtureProvider, "extract", lambda *args: extraction)
    result = upload(client, household)
    assert result.status_code == 201
    receipt = result.json()
    assert receipt["status"] == "draft" and receipt["items"][0]["amount"] is None
    assert receipt["items"][0]["name"] == "Czytelna nazwa"
    tasks = client.get(household["path"] + "/overview?month=2026-10").json()["tasks"]
    assert tasks[0]["kind"] == "extraction"
    assert client.get(household["path"] + "/transactions").json()["items"] == []


def test_all_household_mutations_reject_an_unrelated_user(client, household):
    from test_product import tx

    receipt = upload(client, household).json()
    outsider = TestClient(app)
    assert (
        outsider.post(
            "/auth/register", json={"name": "Other", "email": "outsider@example.com", "password": "outsider-password"}
        ).status_code
        == 201
    )
    root = household["path"]
    category = household["data"]["categories"][0]["id"]
    recurring = {"name": "Payment", "amount": 100, "day": 1, "category_id": category, "account_id": household["data"]["accounts"][0]["id"]}
    operations = [
        ("PUT", "/budget/2026-10", {"planned_income": 100, "allocations": []}),
        ("POST", "/transactions", tx(household)),
        ("PUT", "/transactions/unknown/allocations", [{"category_id": category, "amount": 100}]),
        ("POST", "/goals", {"name": "Goal", "target": 100}),
        ("PUT", "/goals/unknown", {"name": "Goal", "target": 100}),
        ("POST", "/accounts", {"name": "Account"}),
        ("POST", "/categories", {"name": "Category"}),
        ("PATCH", f"/categories/{category}", {"name": "Category"}),
        ("DELETE", f"/categories/{category}", None),
        ("POST", "/recurring", recurring),
        ("PUT", "/recurring/unknown", recurring),
        ("POST", "/recurring/unknown/pay/2026-10", None),
        ("PUT", f"/receipts/{receipt['id']}", {"merchant": "Other", "items": []}),
        ("POST", f"/receipts/{receipt['id']}/finalize", finalize(household, receipt)),
        ("DELETE", f"/receipts/{receipt['id']}", None),
        ("DELETE", "/rules/unknown", None),
        ("POST", "/invitations", None),
        ("DELETE", "", {"name": "Testowy dom"}),
    ]
    for method, path, payload in operations:
        result = outsider.request(method, root + path, json=payload, headers={"Idempotency-Key": "unauthorized-write-key"})
        assert result.status_code == 403, (method, path, result.status_code)
    assert upload(outsider, household).status_code == 403


def test_same_receipt_different_photo_requires_explicit_separate_purchase(client, household):
    first = upload(client, household).json()
    payload = finalize(household, first)
    assert client.post(household["path"] + "/receipts/" + first["id"] + "/finalize", json=payload).status_code == 200
    second = client.post(
        household["path"] + "/receipts",
        files={"file": ("different-photo.png", (ROOT / "apps/web/public/icon-192.png").read_bytes(), "image/png")},
    ).json()
    payload["merchant"] = " LIDL "
    response = client.post(household["path"] + "/receipts/" + second["id"] + "/finalize", json=payload)
    assert response.status_code == 409
    assert client.get(household["path"] + "/budget/2026-10").json()["expenses"] == 13975
    payload["acknowledge_duplicate"] = True
    assert client.post(household["path"] + "/receipts/" + second["id"] + "/finalize", json=payload).status_code == 200
    assert client.get(household["path"] + "/budget/2026-10").json()["expenses"] == 27950


def test_concurrent_matching_receipts_with_different_photos_only_count_once(client, household):
    first = upload(client, household).json()
    second = client.post(
        household["path"] + "/receipts",
        files={"file": ("other-photo.png", (ROOT / "apps/web/public/icon-192.png").read_bytes(), "image/png")},
    ).json()
    payload = finalize(household, first)
    cookies = dict(client.cookies)

    def submit(receipt):
        with TestClient(app) as parallel:
            parallel.cookies.update(cookies)
            return parallel.post(household["path"] + "/receipts/" + receipt["id"] + "/finalize", json=payload)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, [first, second]))
    assert sorted(r.status_code for r in results) == [200, 409]
    assert client.get(household["path"] + "/budget/2026-10").json()["expenses"] == 13975


def test_different_receipt_photo_matching_headers_creates_duplicate_review(client, household, monkeypatch):
    from app.receipts import FixtureProvider

    original = FixtureProvider.extract
    first = upload(client, household).json()
    monkeypatch.setattr(
        FixtureProvider, "extract", lambda self, image, categories: original(self, (ROOT / "fixtures/lidl.png").read_bytes(), categories)
    )
    second = client.post(
        household["path"] + "/receipts",
        files={"file": ("other-photo.png", (ROOT / "apps/web/public/icon-192.png").read_bytes(), "image/png")},
    ).json()
    assert second["id"] != first["id"] and second["status"] == "ready"
    tasks = client.get(household["path"] + "/overview?month=2026-10").json()["tasks"]
    assert any(t["receipt_id"] == second["id"] and t["kind"] == "duplicate" for t in tasks)


def test_receipt_duplicate_suspicion_never_crosses_households(client, household):
    first = upload(client, household).json()
    assert client.post(household["path"] + "/receipts/" + first["id"] + "/finalize", json=finalize(household, first)).status_code == 200
    other = client.post("/households", json={"name": "Other receipt home"}, headers={"Idempotency-Key": "other-receipt-home-key"}).json()
    home = {"id": other["id"], "path": "/households/" + other["id"]}
    home["data"] = client.get(home["path"] + "/overview?month=2026-10").json()
    second = upload(client, home).json()
    tasks = client.get(home["path"] + "/overview?month=2026-10").json()["tasks"]
    assert not any(t["kind"] == "duplicate" for t in tasks)
    assert client.post(home["path"] + "/receipts/" + second["id"] + "/finalize", json=finalize(home, second)).status_code == 200


def test_corrected_draft_adds_and_clears_semantic_duplicate_inbox(client, household):
    first = upload(client, household).json()
    payload = finalize(household, first)
    assert client.post(household["path"] + "/receipts/" + first["id"] + "/finalize", json=payload).status_code == 200
    second = client.post(
        household["path"] + "/receipts", files={"file": ("other.png", (ROOT / "apps/web/public/icon-192.png").read_bytes(), "image/png")}
    ).json()
    draft = {k: v for k, v in payload.items() if k != "account_id"}
    path = household["path"] + "/receipts/" + second["id"]
    assert client.put(path, json=draft).status_code == 200
    tasks = client.get(household["path"] + "/overview?month=2026-10").json()["tasks"]
    assert any(t["receipt_id"] == second["id"] and t["kind"] == "duplicate" for t in tasks)
    draft["merchant"] = "Inny sklep"
    assert client.put(path, json=draft).status_code == 200
    tasks = client.get(household["path"] + "/overview?month=2026-10").json()["tasks"]
    assert not any(t["receipt_id"] == second["id"] and t["kind"] == "duplicate" for t in tasks)
    assert client.get(household["path"] + "/budget/2026-10").json()["expenses"] == 13975


def test_readable_receipt_without_quantity_needs_no_invented_quantity(client, household, monkeypatch):
    from app.receipts import FixtureProvider

    category = household["data"]["categories"][0]["id"]
    extraction = Extraction(
        merchant="Brak ilości",
        date="2026-10-05",
        total=100,
        items=[{"name": "Produkt", "quantity": None, "amount": 100, "category_id": category, "confidence": 99}],
    )
    monkeypatch.setattr(FixtureProvider, "extract", lambda *args: extraction)
    receipt = upload(client, household).json()
    assert receipt["status"] == "ready" and receipt["items"][0]["quantity"] == ""
    response = client.post(household["path"] + "/receipts/" + receipt["id"] + "/finalize", json=finalize(household, receipt))
    assert response.status_code == 200 and response.json()["amount"] == 100
