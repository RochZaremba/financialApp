"""Synthetic provider for disposable browser QA. This script is not in production images."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).absolute().parents[1] / "apps/api"))

import uvicorn  # noqa: E402
from fastapi import Depends, HTTPException  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app import bank_sync  # noqa: E402
from app.bank_provider import EnableBanking, config_path, load_config  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.domain import today  # noqa: E402
from app.main import app  # noqa: E402
from app.models import BankConnection, BankDelivery, User  # noqa: E402
from app.security import current_user  # noqa: E402

if settings.app_env != "development" or not engine.url.database.endswith("_test"):
    raise SystemExit("Bank QA refuses non-disposable environments")

phase = 0


def call(self, method, path, data=None, params=None):
    if path == "/application":
        return {"active": True, "environment": "PRODUCTION", "services": ["AIS"]}
    if path == "/aspsps":
        return {"aspsps": [{"name": "mBank", "country": "PL", "psu_types": ["personal"], "maximum_consent_validity": 90 * 86400}]}
    if path == "/auth":
        return {"url": "https://bank.qa.invalid/?state=" + data["state"]}
    if path == "/sessions" and method == "POST":
        return dict(
            session_id="qa-private-session",
            aspsp={"name": "mBank", "country": "PL"},
            psu_type="personal",
            access={"valid_until": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()},
            accounts=[
                dict(
                    uid="account-one", identification_hash="stable-one", currency="PLN", account_id={"iban": "PL00000000000000000000001234"}
                ),
                dict(
                    uid="account-two", identification_hash="stable-two", currency="PLN", account_id={"iban": "PL00000000000000000000004321"}
                ),
            ],
        )
    if path.startswith("/sessions/") and method == "DELETE":
        return {}
    if path.endswith("/balances"):
        return {"balances": [{"balance_type": "ITBD", "balance_amount": {"currency": "PLN", "amount": "1000.00"}}]}
    if path.endswith("/transactions"):
        rows = []

        def row(ref, amount, direction="DBIT", counterpart=""):
            result = dict(
                status="BOOK",
                entry_reference=ref,
                booking_date=today().isoformat(),
                transaction_amount={"amount": amount, "currency": "PLN"},
                credit_debit_indicator=direction,
                creditor={"name": "Sklep QA"},
                debtor={"name": "Wpływ QA"},
                remittance_information=["Opis QA"],
            )
            if counterpart:
                result["creditor_account" if direction == "DBIT" else "debtor_account"] = {"iban": counterpart}
            return result

        if "account-one" in path:
            rows = [row("expense-1", "139.75"), row("income-1", "25.00", "CRDT")]
            if phase:
                rows += [row("expense-2", "5.00"), row("own-transfer", "20.00", counterpart="PL00000000000000000000004321")]
        elif phase:
            rows = [row("own-transfer-credit", "20.00", "CRDT", counterpart="PL00000000000000000000001234")]
        return {"transactions": rows}
    raise AssertionError("Unexpected synthetic provider operation")


EnableBanking.call = call
bank_sync.webpush = lambda **kwargs: None


@app.post("/__qa/admin")
def promote(user=Depends(current_user)):
    with SessionLocal() as db:
        db.get(User, user.id).is_admin = True
        db.commit()
    return {"ok": True}


@app.post("/__qa/reset")
def reset():
    global phase
    phase = 0
    path = config_path()
    if path.parent.name != ".bank" or "artifacts" not in str(path):
        raise HTTPException(400, "QA path guard")
    for name in ("config.json", "provider.pem", "encryption.key", "push.pem"):
        (path.parent / name).unlink(missing_ok=True)
    return {"ok": True}


@app.post("/__qa/advance")
def advance(user=Depends(current_user)):
    global phase
    cfg = load_config()
    if not cfg or user.id != cfg.owner_id:
        raise HTTPException(403)
    phase = 1
    with SessionLocal() as db:
        ids = list(
            db.scalars(select(BankConnection.id).where(BankConnection.household_id == cfg.household_id, BankConnection.status == "active"))
        )
        for identifier in ids:
            db.get(BankConnection, identifier).next_sync = None
        db.commit()
    for identifier in ids:
        bank_sync.sync_connection(cfg, identifier)
    bank_sync.deliver(cfg)
    with SessionLocal() as db:
        return {"delivered": len(list(db.scalars(select(BankDelivery).where(BankDelivery.delivered_at.is_not(None)))))}


uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
