from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from app.config import WARSAW
from test_meters import create, add


def test_exact_hours_daily_average_context_and_edit_preservation(client, household):
    _, path = create(client, household)
    first = add(client, path, "2026-01-01", 100000, time="20:15").json()
    result = add(
        client, path, "2026-01-02", 101000, time="14:15", activities={"cooking": True, "oven": False}, note="Goście, gotowanie obiadu"
    )
    assert result.status_code == 201
    row = result.json()
    detail = client.get(path).json()["readings"][-1]
    assert detail["elapsed_seconds"] == 18 * 3600 and detail["average"] == 1333
    assert detail["from_time"] == "20:15" and detail["time"] == "14:15"
    assert detail["activities"] == {"cooking": True, "oven": False}
    assert detail["note"] == "Goście, gotowanie obiadu"
    # Older MCP/app clients omit the new fields; this must not erase them.
    updated = client.put(
        path + "/readings/" + row["id"], json={"date": row["date"], "value": 102000, "expected_updated_at": row["updated_at"]}
    )
    assert updated.status_code == 200
    assert updated.json()["time"] == row["time"] and updated.json()["note"] == row["note"]
    assert updated.json()["created_at"] == row["created_at"]
    assert client.get(path).json()["readings"][-1]["average"] == 2667
    assert first["time"] == "20:15"
    exported = client.get(household["path"] + "/export").json()["meter_readings"]
    assert any(r["activities"].get("oven") is False and r["note"] == row["note"] for r in exported)


@pytest.mark.parametrize("before,after,value,hours", [("2026-03-28", "2026-03-29", 23000, 23), ("2026-10-24", "2026-10-25", 25000, 25)])
def test_warsaw_daylight_saving_real_elapsed_time(client, household, before, after, value, hours):
    _, path = create(client, household)
    assert add(client, path, before, 0, time="08:00").status_code == 201
    assert add(client, path, after, value, time="08:00").status_code == 201
    row = client.get(path).json()["readings"][-1]
    assert row["elapsed_seconds"] == hours * 3600 and row["average"] == 24000


def test_legacy_unknown_clock_and_explicit_context_clear(client, household):
    _, path = create(client, household)
    assert add(client, path, "2026-01-01", 0).status_code == 201
    row = add(client, path, "2026-01-02", 1000, time="08:00", activities={"oven": False}, note="Opis").json()
    history = client.get(path).json()["readings"]
    assert history[0]["time"] is None and history[0]["activities"] == {} and history[0]["note"] == ""
    assert history[-1]["elapsed_seconds"] is None and history[-1]["average"] == 1000
    cleared = client.put(
        path + "/readings/" + row["id"],
        json={
            "date": row["date"],
            "value": row["value"],
            "time": None,
            "activities": {},
            "note": "",
            "expected_updated_at": row["updated_at"],
        },
    )
    assert cleared.status_code == 200 and cleared.json()["time"] is None and cleared.json()["activities"] == {}


@pytest.mark.parametrize(
    "extra",
    [
        {"time": "24:00"},
        {"time": "8:15"},
        {"time": "12:60"},
        {"time": "12:30:45"},
        {"activities": {"unknown": True}},
        {"activities": {"oven": "false"}},
        {"note": "x" * 241},
    ],
)
def test_context_input_validation(client, household, extra):
    _, path = create(client, household)
    assert add(client, path, "2026-01-01", 0, **extra).status_code == 422


@pytest.mark.parametrize("day", ["2026-03-29", "2026-10-25"])
def test_reject_nonexistent_and_ambiguous_wall_clock(client, household, day):
    _, path = create(client, household)
    assert add(client, path, day, 0, time="02:30").status_code == 422


def test_future_clock_and_context_idempotency(client, household):
    _, path = create(client, household)
    future = datetime.now(WARSAW) + timedelta(minutes=5)
    assert add(client, path, future.date().isoformat(), 0, time=future.strftime("%H:%M")).status_code == 422
    data = {"date": "2026-01-01", "value": 123, "time": "20:00", "activities": {"oven": True}, "note": "Chleb"}
    headers = {"Idempotency-Key": uuid4().hex}
    first = client.post(path + "/readings", json=data, headers=headers)
    assert first.status_code == 201
    assert client.post(path + "/readings", json=data, headers=headers).json()["id"] == first.json()["id"]
    assert client.post(path + "/readings", json={**data, "note": "Inny opis"}, headers=headers).status_code == 409
