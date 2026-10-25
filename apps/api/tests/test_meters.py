import base64
import json
import stat
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from threading import Event
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import meter_vision, meters
from app.config import settings
from app.db import SessionLocal
from app.domain import today
from app.main import app
from app.models import Meter, MeterPhoto, MeterReading, Transaction
from app.receipts import validated_image, storage_path
from app.security import rate_limit

ROOT = Path(__file__).resolve().parents[3]


def create(client, home, **changes):
    response = client.post(
        home["path"] + "/meters", json=(dict(name="Prąd", unit="kWh", interval_days=30) | changes), headers={"Idempotency-Key": uuid4().hex}
    )
    assert response.status_code == 201, response.text
    return response.json(), home["path"] + "/meters/" + response.json()["id"]


def add(client, path, date, value, **changes):
    return client.post(path + "/readings", json=dict(date=date, value=value, **changes), headers={"Idempotency-Key": uuid4().hex})


def photo(client, path, key="meter-photo-operation", image="meter.png"):
    return client.post(
        path + "/photos", files={"file": (image, (ROOT / "fixtures" / image).read_bytes(), "image/png")}, headers={"Idempotency-Key": key}
    )


def test_exact_irregular_intervals_out_of_order_and_zero_not_a_financial_movement(client, household):
    meter, path = create(client, household)
    assert add(client, path, "2026-01-01", 100001).status_code == 201
    first = client.get(path).json()
    assert first["readings"][0]["consumption"] is None and first["readings"][0]["average"] is None
    assert add(client, path, "2026-01-21", 103002).status_code == 201
    assert add(client, path, "2026-01-11", 101002).status_code == 201
    assert add(client, path, "2026-01-22", 103002).status_code == 201
    rows = client.get(path).json()["readings"]
    assert [row["consumption"] for row in rows] == [None, 1001, 2000, 0]
    assert [row["average"] for row in rows] == [None, 100, 200, 0]
    assert rows[-1]["days"] == 1 and rows[0]["created_by_name"] == "Roch"
    assert client.get(household["path"] + "/meters").json()[0]["last_date"] == "2026-01-22"
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Transaction)) == 0


def test_reading_retries_validation_and_exact_day_uniqueness(client, household):
    _, path = create(client, household)
    payload = {"date": "2026-01-01", "value": 1000}
    headers = {"Idempotency-Key": "reading-retry-operation"}
    one = client.post(path + "/readings", json=payload, headers=headers)
    assert one.status_code == 201
    assert client.post(path + "/readings", json=payload, headers=headers).json()["id"] == one.json()["id"]
    assert add(client, path, "2026-01-01", 1000).status_code == 409
    assert add(client, path, "2026-01-02", 999).status_code == 422
    assert add(client, path, "2025-12-01", 1001).status_code == 422
    for value in (-1, True, 1.5, 1_000_000_000_001):
        assert add(client, path, "2026-01-02", value).status_code == 422
    assert add(client, path, (today() + timedelta(days=1)).isoformat(), 1000).status_code == 422
    assert len(client.get(path).json()["readings"]) == 1


def test_edits_and_deletion_recalculate_neighbors_and_reject_stale_revisions(client, household):
    _, path = create(client, household)
    for day, value in ((1, 1000), (11, 2000), (21, 3000)):
        assert add(client, path, f"2026-01-{day:02}", value).status_code == 201
    rows = client.get(path).json()["readings"]
    middle = rows[1]
    payload = dict(date=middle["date"], value=2500, expected_updated_at=middle["updated_at"])
    edited = client.put(path + "/readings/" + middle["id"], json=payload)
    assert edited.status_code == 200 and edited.json()["created_by"] == middle["created_by"]
    assert client.put(path + "/readings/" + middle["id"], json=payload).status_code == 409
    assert (
        client.request("DELETE", path + "/readings/" + middle["id"], json={"expected_updated_at": middle["updated_at"]}).status_code == 409
    )
    assert (
        client.request("DELETE", path + "/readings/" + middle["id"], json={"expected_updated_at": edited.json()["updated_at"]}).status_code
        == 200
    )
    result = client.get(path).json()["readings"]
    assert len(result) == 2 and result[1]["consumption"] == 2000 and result[1]["days"] == 20


def test_private_photo_proposal_explicit_confirmation_and_paid_idempotency(client, household, monkeypatch):
    _, path = create(client, household)
    calls = []

    def extract(image, unit):
        calls.append(unit)
        return dict(value=12345678, unit="kWh", confidence=91)

    monkeypatch.setattr(meters, "extract_meter", extract)
    result = photo(client, path)
    assert result.status_code == 201 and result.json()["proposal"]["value"] == 12345678
    assert "path" not in result.json()
    assert client.get(path).json()["readings"] == []
    saved = result.json()
    with SessionLocal() as db:
        filename = storage_path(db.get(MeterPhoto, saved["id"]).path)
        assert stat.S_IMODE(filename.stat().st_mode) == 0o600
    assert photo(client, path).json()["id"] == saved["id"] and calls == ["kWh"]
    assert photo(client, path, image="lidl.png").status_code == 409
    assert client.get(path + "/photos/" + saved["id"]).headers["content-type"] == "image/png"
    assert add(client, path, "2026-01-01", 12345679, photo_id=saved["id"]).status_code == 201
    assert client.get(path).json()["readings"][0]["value"] == 12345679


def test_household_and_meter_isolation_for_all_operations(client, household):
    _, path = create(client, household)
    other, other_path = create(client, household, name="Drugi")
    saved = photo(client, path).json()
    row = add(client, path, "2026-01-01", 1000).json()
    assert add(client, other_path, "2026-01-01", 1000, photo_id=saved["id"]).status_code == 422
    assert client.get(other_path + "/photos/" + saved["id"]).status_code == 404
    assert (
        client.put(
            other_path + "/readings/" + row["id"], json=dict(date="2026-01-01", value=1001, expected_updated_at=row["updated_at"])
        ).status_code
        == 404
    )
    with TestClient(app) as stranger:
        assert stranger.get(path).status_code == 401
        stranger.post("/auth/register", json={"email": "meter-stranger@example.com", "password": "stranger-password"})
        for url in (household["path"] + "/meters", path, path + "/photos/" + saved["id"]):
            assert stranger.get(url).status_code == 403
        assert add(stranger, path, "2026-01-02", 2000).status_code == 403


def test_optional_plan_and_revision(client, household):
    meter, path = create(client, household)
    assert add(client, path, "2026-01-01", 1).status_code == 201
    assert client.get(path).json()["next_due"] == "2026-01-31"
    data = dict(interval_days=0, expected_updated_at=meter["updated_at"])
    assert client.put(path + "/plan", json=data).status_code == 200
    assert client.get(path).json()["next_due"] is None
    assert client.put(path + "/plan", json=data).status_code == 409


def test_provider_failure_keeps_photo_manual_path_and_safe_codes(client, household, monkeypatch):
    _, path = create(client, household)
    monkeypatch.setattr(settings, "receipt_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", "secret-not-to-be-logged")

    def fail(*args, **kwargs):
        request = httpx.Request("POST", "https://provider.example")
        return httpx.Response(429, json={"error": {"status": "RESOURCE_EXHAUSTED", "message": "secret-not-to-be-logged"}}, request=request)

    monkeypatch.setattr(meter_vision.httpx, "post", fail)
    saved = photo(client, path).json()
    assert saved["proposal"] is None and saved["diagnostics"]["code"] == "RESOURCE_EXHAUSTED"
    assert saved["diagnostics"]["http_status"] == 429 and "secret-not-to-be-logged" not in str(saved)
    assert client.get(path + "/photos/" + saved["id"]).status_code == 200
    assert add(client, path, "2026-01-01", 123, photo_id=saved["id"]).status_code == 201


def test_fixture_never_invents_a_reading_from_arbitrary_image_and_manual_uploads_work(client, household, monkeypatch):
    _, path = create(client, household)
    assert photo(client, path).json()["proposal"]["value"] == 12345678
    assert photo(client, path, key="not-a-meter-image", image="lidl.png").json()["proposal"] is None
    monkeypatch.setattr(settings, "receipt_provider", "manual")
    assert photo(client, path, key="manual-meter-image").json()["proposal"] is None
    assert (
        client.post(path + "/photos", files={"file": ("bad.png", b"not an image")}, headers={"Idempotency-Key": uuid4().hex}).status_code
        == 422
    )


def test_storage_filename_collision_cannot_remove_an_existing_photo(client, household, monkeypatch):
    _, path = create(client, household)
    saved = photo(client, path).json()
    with SessionLocal() as db:
        name = db.get(MeterPhoto, saved["id"]).path
    destination = storage_path(name)
    original = destination.read_bytes()
    monkeypatch.setattr(meters.secrets, "token_hex", lambda size: name.removeprefix("meter-").removesuffix(".png"))
    with pytest.raises(FileExistsError):
        photo(client, path, key="different-upload-operation")
    assert destination.read_bytes() == original


def test_export_and_household_deletion_include_meter_data_and_private_photos(client, household):
    _, path = create(client, household)
    saved = photo(client, path).json()
    add(client, path, "2026-01-01", 100, photo_id=saved["id"])
    with SessionLocal() as db:
        filename = storage_path(db.get(MeterPhoto, saved["id"]).path)
    exported = client.get(household["path"] + "/export").json()
    assert len(exported["meters"]) == len(exported["meter_photos"]) == len(exported["meter_readings"]) == 1
    assert "path" not in exported["meter_photos"][0]
    response = client.request("DELETE", household["path"], json={"name": "Testowy dom"})
    assert response.status_code == 200 and not filename.exists()


def test_photo_limits_are_shared_with_receipt_ocr(client, household):
    _, path = create(client, household)
    person = client.get("/auth/me").json()["user"]["id"]
    for _ in range(12):
        rate_limit(f"receipts:{person}", 12, 3600)
    assert photo(client, path).status_code == 429


def test_bounded_history_retains_all_records_in_export(client, household):
    meter, path = create(client, household)
    from datetime import date

    with SessionLocal() as db:
        db.add_all(
            [
                MeterReading(household_id=household["id"], meter_id=meter["id"], date=date(2020, 1, 1) + timedelta(days=i), value=i * 1000)
                for i in range(501)
            ]
        )
        db.commit()
    result = client.get(path).json()
    assert result["truncated"] is True and len(result["readings"]) == 500
    assert result["readings"][0]["value"] == 1000 and result["readings"][0]["consumption"] is None
    assert len(client.get(household["path"] + "/export").json()["meter_readings"]) == 501


def test_meter_limit_does_not_break_a_committed_creation_retry(client, household):
    payload = dict(name="Pierwszy", unit="kWh", interval_days=0)
    headers = {"Idempotency-Key": "first-meter-operation"}
    url = household["path"] + "/meters"
    original = client.post(url, json=payload, headers=headers).json()
    with SessionLocal() as db:
        db.add_all([Meter(household_id=household["id"], name=f"Licznik {i}", unit="m3", interval_days=0) for i in range(29)])
        db.commit()
    assert client.post(url, json=payload, headers=headers).json()["id"] == original["id"]
    assert client.post(url, json=payload, headers={"Idempotency-Key": uuid4().hex}).status_code == 409


def test_concurrent_readings_cannot_create_a_decreasing_history(client, household):
    _, path = create(client, household)
    add(client, path, "2026-01-01", 0)

    def attempt(args):
        with TestClient(app) as contender:
            contender.cookies.update(client.cookies)
            return add(contender, path, *args).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(attempt, [("2026-01-02", 3000), ("2026-01-03", 2000)]))
    assert sorted(statuses) == [201, 422]


def test_concurrent_photo_retries_do_not_repeat_provider_call(client, household, monkeypatch):
    _, path = create(client, household)
    started, finish = Event(), Event()
    calls = []

    def extract(image, unit):
        calls.append(unit)
        started.set()
        assert finish.wait(10)
        return dict(value=1000, unit="kWh", confidence=100)

    monkeypatch.setattr(meters, "extract_meter", extract)

    def first():
        with TestClient(app) as contender:
            contender.cookies.update(client.cookies)
            return photo(contender, path)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(first)
        try:
            assert started.wait(5)
            assert photo(client, path).status_code == 409
        finally:
            finish.set()
        assert future.result().status_code == 201
    assert photo(client, path).status_code == 201 and calls == ["kWh"]


@pytest.mark.parametrize(
    "value,unit,finish,valid",
    [
        ("12.345", "kWh", "STOP", True),
        (None, None, "STOP", True),
        ("1.2345", "kWh", "STOP", False),
        ("-1", "kWh", "STOP", False),
        ("1", "m3", "STOP", False),
        ("1", "kWh", "MAX_TOKENS", False),
    ],
)
def test_gemini_structured_meter_output_is_strict(monkeypatch, value, unit, finish, valid):
    monkeypatch.setattr(settings, "receipt_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    image = validated_image((ROOT / "fixtures/meter.png").read_bytes())

    def response(url, **kwargs):
        assert kwargs["json"]["contents"][0]["parts"][1]["inlineData"]["data"] == base64.b64encode(image).decode()
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"finishReason": finish, "content": {"parts": [{"text": json.dumps(dict(value=value, unit=unit, confidence=91))}]}}
                ]
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(meter_vision.httpx, "post", response)
    if valid:
        result = meter_vision.extract_meter(image, "kWh")
        assert result["value"] == (12345 if value is not None else None)
    else:
        with pytest.raises(ValueError):
            meter_vision.extract_meter(image, "kWh")


def test_openai_meter_contract_disables_storage_and_validates_output(monkeypatch):
    monkeypatch.setattr(settings, "receipt_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "test-key")

    def response(url, **kwargs):
        assert kwargs["json"]["store"] is False
        assert kwargs["json"]["text"]["format"]["strict"] is True
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [{"content": [{"type": "output_text", "text": '{"value":"1.001","unit":"m3","confidence":80}'}]}],
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(meter_vision.httpx, "post", response)
    assert meter_vision.extract_meter(b"sanitized-image", "m3")["value"] == 1001
