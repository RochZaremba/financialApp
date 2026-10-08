"""Indicative NBP account valuation; never changes booked PLN transactions."""

import json
import time
from datetime import date, datetime
from decimal import Decimal, DecimalException, ROUND_HALF_UP
from threading import Lock

import httpx

from .config import WARSAW

CURRENCIES = ("PLN", "EUR", "USD", "GBP", "CHF")
_lock = Lock()
_rates: dict[str, Decimal] = {}
_rate_date: str | None = None
_retry_at = 0.0
_failed = False


def fetch_table():
    response = httpx.get("https://api.nbp.pl/api/exchangerates/tables/A/?format=json", timeout=3)
    response.raise_for_status()
    table = json.loads(response.text, parse_float=Decimal)[0]
    published = date.fromisoformat(table["effectiveDate"])
    if published > datetime.now(WARSAW).date():
        raise ValueError("Future exchange table")
    rates = {r["code"]: Decimal(str(r["mid"])) for r in table["rates"] if r["code"] in CURRENCIES[1:]}
    if set(rates) != set(CURRENCIES[1:]) or any(not r.is_finite() or not Decimal("0.0001") <= r <= 1000 for r in rates.values()):
        raise ValueError("Incomplete or invalid exchange table")
    return rates, published.isoformat()


def latest_rates():
    global _rates, _rate_date, _retry_at, _failed
    with _lock:
        if time.monotonic() >= _retry_at:
            try:
                rates, published = fetch_table()
                _rates, _rate_date = rates, published
                _failed = False
                _retry_at = time.monotonic() + 3600
            except (httpx.HTTPError, DecimalException, ValueError, KeyError, TypeError, IndexError):
                _failed = True
                _retry_at = time.monotonic() + 60
        return dict(_rates), _rate_date, _failed


def value_accounts(accounts):
    rates, published, failed = latest_rates() if any(a["currency"] != "PLN" for a in accounts) else ({}, None, False)
    for account in accounts:
        rate = Decimal(1) if account["currency"] == "PLN" else rates.get(account["currency"])
        account["balance_pln"] = int((account["balance"] * rate).quantize(Decimal(1), rounding=ROUND_HALF_UP)) if rate else None
        account["exchange_rate"] = str(rate) if rate else None
    total = sum(a["balance_pln"] for a in accounts) if all(a["balance_pln"] is not None for a in accounts) else None
    return {"total_pln": total, "rate_date": published, "status": "unavailable" if total is None else "cached" if failed else "current"}
