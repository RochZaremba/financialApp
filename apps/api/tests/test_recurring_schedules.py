from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.schedules import occurrence_dates


@pytest.mark.parametrize(
    "frequency,anchor,day,start,end,expected",
    [
        ("monthly", date(2026, 1, 1), 31, date(2026, 2, 1), date(2026, 3, 31), [date(2026, 2, 28), date(2026, 3, 31)]),
        (
            "yearly",
            date(2024, 2, 29),
            29,
            date(2025, 1, 1),
            date(2028, 12, 31),
            [date(2025, 2, 28), date(2026, 2, 28), date(2027, 2, 28), date(2028, 2, 29)],
        ),
        (
            "quarterly",
            date(2026, 1, 31),
            31,
            date(2026, 1, 1),
            date(2026, 12, 31),
            [date(2026, 1, 31), date(2026, 4, 30), date(2026, 7, 31), date(2026, 10, 31)],
        ),
        (
            "weekly",
            date(2026, 9, 25),
            25,
            date(2026, 10, 1),
            date(2026, 10, 31),
            [date(2026, 10, 2), date(2026, 10, 9), date(2026, 10, 16), date(2026, 10, 23), date(2026, 10, 30)],
        ),
    ],
)
def test_schedule_boundaries_retain_anchor(frequency, anchor, day, start, end, expected):
    assert occurrence_dates(SimpleNamespace(frequency=frequency, start_date=anchor, day=day), start, end) == expected


def recurring(client, home, **changes):
    payload = dict(
        name="Płatność", amount=12345, day=2, category_id=home["data"]["categories"][0]["id"], account_id=home["data"]["accounts"][0]["id"]
    )
    payload.update(changes)
    return client.post(home["path"] + "/recurring", json=payload, headers={"Idempotency-Key": str(uuid4())})


def test_weekly_occurrences_paid_once_and_forecast(client, household, monkeypatch):
    row = recurring(client, household, frequency="weekly", start_date="2026-10-02").json()
    view = client.get(household["path"] + "/overview?month=2026-10").json()
    assert len(view["recurring"]) == 5 and all(r["scheduled"] for r in view["recurring"])
    endpoint = household["path"] + "/recurring/" + row["id"] + "/pay/"
    assert client.post(endpoint + "2026-10").status_code == 422
    assert client.post(endpoint + "2026-10-03").status_code == 422
    first = client.post(endpoint + "2026-10-02")
    assert first.status_code == 200
    assert client.post(endpoint + "2026-10-02").json()["id"] == first.json()["id"]
    assert client.post(endpoint + "2026-10-09").status_code == 200
    view = client.get(household["path"] + "/overview?month=2026-10").json()
    assert sum(r["paid"] for r in view["recurring"]) == 2
    assert view["budget"]["expenses"] == 24690
    assert client.get(household["path"] + "/analytics?month=2026-10").json()["outstanding_recurring"] == 37035


def test_annual_not_due_stays_manageable_and_is_not_in_forecast(client, household):
    row = recurring(client, household, frequency="yearly", start_date="2026-01-31", reminder_days=7).json()
    view = client.get(household["path"] + "/overview?month=2026-10").json()
    assert len(view["recurring"]) == 1
    assert not view["recurring"][0]["scheduled"] and view["recurring"][0]["due_date"] == "2027-01-31"
    assert client.get(household["path"] + "/analytics?month=2026-10").json()["outstanding_recurring"] == 0
    assert client.post(household["path"] + "/recurring/" + row["id"] + "/pay/2026-10").status_code == 422


def test_reminders_resolve_without_booking_expectations(client, household, monkeypatch):
    monkeypatch.setattr("app.main.today", lambda: date(2026, 10, 8))
    monthly = recurring(client, household, day=6, start_date="2026-10-01", reminder_days=3).json()
    upcoming = recurring(client, household, day=10, start_date="2026-10-01", name="Internet").json()
    assert not client.get(household["path"] + "/transactions").json()["items"]
    reminders = client.get(household["path"] + "/reminders").json()
    assert [r["reminder_status"] for r in reminders] == ["overdue", "upcoming"]
    assert client.post(household["path"] + "/recurring/" + monthly["id"] + "/pay/2026-10-06").status_code == 200
    assert [r["id"] for r in client.get(household["path"] + "/reminders").json()] == [upcoming["id"]]


def test_calendar_alarms_escaping_authorization_and_validation(client, household, monkeypatch):
    monkeypatch.setattr("app.main.today", lambda: date(2026, 10, 1))
    assert (
        recurring(client, household, frequency="yearly", start_date="2026-10-15", reminder_days=7, name="Łódź; rachunek, dom").status_code
        == 201
    )
    response = client.get(household["path"] + "/recurring/calendar")
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/calendar")
    content = response.content.decode()
    assert "DTSTART;VALUE=DATE:20261015" in content and "TRIGGER:-P7D" in content
    assert "SUMMARY:Łódź\\; rachunek\\, dom" in content
    assert all(len(line.encode()) <= 75 for line in content.split("\r\n"))
    assert content.startswith("BEGIN:VCALENDAR\r\n") and content.endswith("END:VCALENDAR\r\n")
    for changes in [dict(frequency="yearly"), dict(frequency="unsafe"), dict(reminder_days=31), dict(start_date="1999-01-01")]:
        assert recurring(client, household, **changes).status_code == 422
    outsider = TestClient(app)
    assert (
        outsider.post("/auth/register", json={"email": "calendar-other@example.com", "password": "private-password-long"}).status_code
        == 201
    )
    assert outsider.get(household["path"] + "/recurring/calendar").status_code == 403
    assert outsider.get(household["path"] + "/reminders").status_code == 403
