import uuid
from decimal import Decimal

import httpx
import pytest

from app import exchange


@pytest.fixture
def rates(monkeypatch):
    monkeypatch.setattr(exchange, "_rates", {})
    monkeypatch.setattr(exchange, "_rate_date", None)
    monkeypatch.setattr(exchange, "_retry_at", 0)
    monkeypatch.setattr(exchange, "_failed", False)
    calls = []

    def fetch():
        calls.append(1)
        return {code: Decimal("4.12345") for code in exchange.CURRENCIES[1:]}, "2026-10-07"

    monkeypatch.setattr(exchange, "fetch_table", fetch)
    return calls


def test_precise_signed_valuation_and_cache(rates):
    accounts = [dict(currency="EUR", balance=100), dict(currency="CHF", balance=-100), dict(currency="PLN", balance=123)]
    assert exchange.value_accounts(accounts)["total_pln"] == 123
    assert [a["balance_pln"] for a in accounts] == [412, -412, 123]
    exchange.value_accounts(accounts)
    assert len(rates) == 1
    accounts = [dict(currency="EUR", balance=1)]
    exchange._rates["EUR"] = Decimal("4.5")
    assert exchange.value_accounts(accounts)["total_pln"] == 5
    accounts[0]["balance"] = -1
    assert exchange.value_accounts(accounts)["total_pln"] == -5


def test_outage_never_shows_partial_total(rates, monkeypatch):
    def fail():
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(exchange, "fetch_table", fail)
    accounts = [dict(currency="PLN", balance=123), dict(currency="EUR", balance=100)]
    result = exchange.value_accounts(accounts)
    assert result == dict(total_pln=None, rate_date=None, status="unavailable")
    assert accounts[0]["balance_pln"] == 123
    exchange._rates = {"EUR": Decimal("4.5")}
    exchange._rate_date = "2026-10-07"
    exchange._retry_at = 0
    assert exchange.value_accounts(accounts) == dict(total_pln=573, rate_date="2026-10-07", status="cached")


@pytest.mark.parametrize("rate", ["NaN", "-1", "0", "1001"])
def test_invalid_provider_rates_rejected(monkeypatch, rate):
    payload = (
        '[{"effectiveDate":"2026-01-01","rates":['
        + ",".join('{"code":"' + code + '","mid":' + rate + "}" for code in exchange.CURRENCIES[1:])
        + "]}]"
    )
    monkeypatch.setattr(
        exchange.httpx, "get", lambda *a, **kw: httpx.Response(200, text=payload, request=httpx.Request("GET", "https://api.nbp.pl"))
    )
    with pytest.raises(ValueError):
        exchange.fetch_table()


def test_currency_accounts_and_pln_write_boundaries(client, household, rates):
    path = household["path"]
    key = {"Idempotency-Key": str(uuid.uuid4())}
    body = dict(name="Euro", currency="EUR", opening_balance=10000)
    response = client.post(path + "/accounts", json=body, headers=key)
    assert response.status_code == 201
    foreign = response.json()["id"]
    assert client.post(path + "/accounts", json=body, headers=key).json()["id"] == foreign
    assert (
        client.post(path + "/accounts", json={**body, "currency": "XYZ"}, headers={"Idempotency-Key": str(uuid.uuid4())}).status_code == 422
    )
    data = client.get(path + "/overview?month=2026-10").json()
    assert data["account_valuation"]["total_pln"] == 41235
    assert len([a for a in data["accounts"] if a["currency"] == "EUR"]) == 1
    assert all(a["currency"] == "PLN" for a in data["accounts"] if a["id"] != foreign)
    account = household["data"]["accounts"][0]["id"]
    for source, destination, kind in [(foreign, None, "income"), (account, foreign, "transfer")]:
        tx = dict(kind=kind, account_id=source, amount=100, date="2026-10-08", description="Test", allocations=[])
        if destination:
            tx["destination_id"] = destination
        assert client.post(path + "/transactions", json=tx, headers={"Idempotency-Key": str(uuid.uuid4())}).status_code == 422
    recurring = dict(name="Euro bill", amount=100, day=1, account_id=foreign, category_id=data["categories"][0]["id"])
    assert client.post(path + "/recurring", json=recurring, headers={"Idempotency-Key": str(uuid.uuid4())}).status_code == 422
    # Account write is household-authorized even when currency is supported.
    assert client.post("/households/foreign/accounts", json=body, headers={"Idempotency-Key": str(uuid.uuid4())}).status_code == 403


def test_rate_refresh_and_bad_response_throttled(rates, monkeypatch):
    account = [dict(currency="EUR", balance=100)]
    exchange.value_accounts(account)
    exchange._retry_at = 0
    monkeypatch.setattr(exchange, "fetch_table", lambda: ({"EUR": Decimal("4.5")}, "2026-10-08"))
    assert exchange.value_accounts(account)["total_pln"] == 450
    assert exchange._rate_date == "2026-10-08"
    exchange._retry_at = 0
    calls = []

    def bad_response():
        calls.append(1)
        return Decimal("not-a-number")

    monkeypatch.setattr(exchange, "fetch_table", bad_response)
    assert exchange.value_accounts(account)["status"] == "cached"
    assert exchange.value_accounts(account)["status"] == "cached"
    assert len(calls) == 1


def test_provider_json_keeps_decimal_precision(monkeypatch):
    payload = (
        '[{"effectiveDate":"2026-01-01","rates":['
        + ",".join('{"code":"' + code + '","mid":4.12345}' for code in exchange.CURRENCIES[1:])
        + "]}]"
    )
    monkeypatch.setattr(
        exchange.httpx, "get", lambda *a, **kw: httpx.Response(200, text=payload, request=httpx.Request("GET", "https://api.nbp.pl"))
    )
    rates, published = exchange.fetch_table()
    assert published == "2026-01-01"
    assert rates["EUR"] == Decimal("4.12345")


def test_account_currency_migration_preserves_balances_and_refuses_loss(client, household):
    import os
    import subprocess
    import sys
    from pathlib import Path

    from app.db import engine

    env = {**os.environ, "DATABASE_URL": engine.url.render_as_string(hide_password=False)}

    def migrate(*args):
        return subprocess.run(
            [sys.executable, "-m", "alembic", *args], cwd=Path(__file__).resolve().parents[1], env=env, capture_output=True
        )

    assert migrate("downgrade", "005").returncode == 0
    try:
        assert migrate("upgrade", "head").returncode == 0
        accounts = client.get(household["path"] + "/overview?month=2026-10").json()["accounts"]
        assert [(a["id"], a["balance"]) for a in accounts] == [(a["id"], a["balance"]) for a in household["data"]["accounts"]]
        assert all(a["currency"] == "PLN" for a in accounts)
        assert (
            client.post(
                household["path"] + "/accounts",
                json=dict(name="EUR", currency="EUR", opening_balance=-1),
                headers={"Idempotency-Key": str(uuid.uuid4())},
            ).status_code
            == 201
        )
        assert migrate("downgrade", "005").returncode != 0
        exported = client.get(household["path"] + "/export").json()
        assert any(a["currency"] == "EUR" and a["opening_balance"] == -1 for a in exported["accounts"])
    finally:
        assert migrate("upgrade", "head").returncode == 0
