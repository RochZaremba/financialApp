import base64
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
import httpx
from app import bank_provider
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, text

from app import bank_sync
from app.bank_provider import BankConfig, BankError, EnableBanking, minor_amount
from app.config import settings
from app.db import SessionLocal
from app.domain import today
from app.main import app
from app.models import (
    BankAccount,
    BankConnection,
    BankDelivery,
    BankEntry,
    BankSubscription,
    Household,
    Member,
    Transaction,
    TransactionAllocation,
    User,
)

PASSWORD = "bank-test-user-password"


@pytest.fixture
def configured(client, household, tmp_path, monkeypatch):
    owner = client.get("/auth/me").json()["user"]["id"]
    with SessionLocal() as db:
        second = User(name="Kaja QA", email="bank-second@example.com", password_hash="unused-test-hash")
        db.add(second)
        db.flush()
        db.add(Member(household_id=household["id"], user_id=second.id))
        db.commit()
        second_id = second.id
    folder = tmp_path / "private"
    folder.mkdir(mode=0o700)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    push = ec.generate_private_key(ec.SECP256R1())
    paths = [folder / name for name in ["provider.pem", "encryption.key", "push.pem"]]
    values = [
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()),
        Fernet.generate_key(),
        push.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()),
    ]
    for p, v in zip(paths, values, strict=True):
        p.write_bytes(v)
        p.chmod(0o600)
    public = (
        base64.urlsafe_b64encode(push.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))
        .decode()
        .rstrip("=")
    )
    cfg = BankConfig(
        household_id=household["id"],
        owner_id=owner,
        allowed_users=[owner, second_id],
        app_id=str(uuid4()),
        private_key_path=str(paths[0]),
        encryption_key_path=str(paths[1]),
        vapid_key_path=str(paths[2]),
        vapid_public_key=public,
        contact_email="owner@example.com",
    )
    config = folder / "config.json"
    config.write_text(json.dumps(cfg.__dict__))
    config.chmod(0o600)
    monkeypatch.setattr(settings, "bank_config_path", str(config))
    return cfg


def make_account(home, cfg, *, balance_at=None, initial=False):
    with SessionLocal() as db:
        c = BankConnection(
            household_id=home["id"],
            user_id=cfg.owner_id,
            status="active",
            session_cipher=cfg.seal("private-session"),
            valid_until=datetime.now(timezone.utc) + timedelta(days=30),
        )
        db.add(c)
        db.flush()
        a = BankAccount(
            household_id=home["id"],
            connection_id=c.id,
            uid_cipher=cfg.seal("private-provider-account"),
            identity_hash="a" * 64,
            last4="1234",
            currency="PLN",
            account_id=home["data"]["accounts"][0]["id"],
            start_date=today() - timedelta(days=30),
            balance_at=balance_at,
            last_sync=None if initial else datetime.now(timezone.utc),
        )
        db.add(a)
        db.commit()
        return c.id, a.id


def raw(reference="ref-1", amount="12.34", direction="DBIT", **changes):
    return dict(
        status="BOOK",
        entry_reference=reference,
        booking_date=today().isoformat(),
        transaction_amount={"amount": amount, "currency": "PLN"},
        credit_debit_indicator=direction,
        creditor={"name": "Sklep QA"},
        remittance_information=["Zakupy"],
        **changes,
    )


def fake_feed(monkeypatch, rows):
    monkeypatch.setattr(EnableBanking, "transactions", lambda self, *args: rows)
    monkeypatch.setattr(
        EnableBanking, "balances", lambda self, *args: [dict(balance_type="ITBD", balance_amount={"currency": "PLN", "amount": "100.00"})]
    )


def due(identifier):
    with SessionLocal() as db:
        db.get(BankConnection, identifier).next_sync = None
        db.commit()


def test_disabled_by_default_and_exact_household_user_binding(client, household, configured):
    path = household["path"] + "/bank"
    assert client.get(path).json()["enabled"]
    original = Path(settings.bank_config_path)
    original.chmod(0o644)
    assert client.get(path).json() == {"enabled": False}
    original.chmod(0o600)
    connection, _ = make_account(household, configured)
    # Even a new member of the same home cannot export the private bank feed.
    with TestClient(app) as other:
        other.post("/auth/register", json={"email": "third@example.com", "password": PASSWORD})
        assert other.get(path).status_code == 403
        identifier = other.get("/auth/me").json()["user"]["id"]
        with SessionLocal() as db:
            db.add(Member(household_id=household["id"], user_id=identifier))
            db.commit()
        assert other.get(path).json() == {"enabled": False}
        assert other.post(path + "/connect").status_code == 404
        assert other.get(household["path"] + "/export").json()["bank_accounts"] == []
    second = client.post("/households", json={"name": "Other house"}, headers={"Idempotency-Key": uuid4().hex}).json()
    assert client.get(f"/households/{second['id']}/bank").json() == {"enabled": False}
    names = {tool for tool in app.state.mcp_operations}
    assert not any(name.startswith("bank_") or name in ("subscribe", "unsubscribe", "receipt_matches") for name in names)


def test_automatic_exact_expense_durable_retry_quota_and_private_export(client, household, configured, monkeypatch):
    connection, account = make_account(household, configured)
    fake_feed(monkeypatch, [raw()])
    assert bank_sync.sync_connection(configured, connection)
    with SessionLocal() as db:
        e = db.scalar(select(BankEntry))
        tx = db.get(Transaction, e.transaction_id)
        assert e.amount == -1234 and tx.amount == 1234 and tx.status == "unallocated" and tx.source == "bank"
        assert db.scalar(select(BankAccount)).balance == 10000
    assert not bank_sync.sync_connection(configured, connection)
    due(connection)
    assert bank_sync.sync_connection(configured, connection)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(BankEntry)) == 1
        assert db.scalar(select(func.count()).select_from(Transaction)) == 1
    response = client.get(household["path"] + "/bank")
    assert response.status_code == 200
    assert "private-session" not in response.text and "cipher" not in response.text
    exported = client.get(household["path"] + "/export")
    assert len(exported.json()["bank_entries"]) == 1 and "cipher" not in exported.text


def test_unique_manual_candidate_is_linked_automatically(client, household, configured, monkeypatch):
    amount = 1234
    account = household["data"]["accounts"][0]["id"]
    tx = client.post(
        household["path"] + "/transactions",
        json={"kind": "expense", "amount": amount, "date": today().isoformat(), "description": "Ręczny wydatek", "account_id": account},
        headers={"Idempotency-Key": uuid4().hex},
    ).json()
    connection, _ = make_account(household, configured)
    fake_feed(monkeypatch, [raw()])
    assert bank_sync.sync_connection(configured, connection)
    status = client.get(household["path"] + "/bank").json()
    entry = status["entries"][0]
    assert entry["transaction"]["id"] == tx["id"] and entry["reviewed"] and entry["match_method"] == "unique"
    assert client.post(household["path"] + "/bank/reconcile").json() == {"matched": 0, "refunds": 0}
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Transaction)) == 1


def test_credits_and_uncertain_duplicates_stay_for_review(client, household, configured, monkeypatch):
    connection, _ = make_account(household, configured)
    fake_feed(monkeypatch, [raw(None), raw(None), raw("credit", direction="CRDT"), {**raw("pending"), "status": "PDNG"}])
    assert bank_sync.sync_connection(configured, connection)
    due(connection)
    assert bank_sync.sync_connection(configured, connection)
    with SessionLocal() as db:
        entries = list(db.scalars(select(BankEntry)))
        assert len(entries) == 3 and all(e.transaction_id is None for e in entries)
        assert sum(not e.reliable for e in entries) == 2


def test_partial_failure_preserves_cursor_and_bank_identity_conflicts(client, household, configured, monkeypatch):
    connection, account = make_account(household, configured)
    fake_feed(monkeypatch, [raw()])
    assert bank_sync.sync_connection(configured, connection)
    fake_feed(monkeypatch, [raw("new", amount="1.00"), raw(amount="99.00")])
    due(connection)
    assert not bank_sync.sync_connection(configured, connection)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(BankEntry)) == 1
        assert db.scalar(select(func.count()).select_from(Transaction)) == 1
        c = db.get(BankConnection, connection)
        assert c.error_code == "BANK_ENTRY_CHANGED" and c.next_sync


@pytest.mark.parametrize("iban", ["PL-TEST-1234", None])
def test_authorization_state_nonce_and_reconnect_mapping(client, household, configured, monkeypatch, iban):
    states = []
    monkeypatch.setattr(
        EnableBanking, "banks", lambda self: [dict(name="mBank", country="PL", psu_types=["personal"], maximum_consent_validity=15552000)]
    )

    def authorize(self, state, until, name):
        states.append(state)
        return {"url": "https://enablebanking.com/auth-test"}

    monkeypatch.setattr(EnableBanking, "authorize", authorize)
    monkeypatch.setattr(
        EnableBanking,
        "session",
        lambda self, code: dict(
            session_id="one-session",
            aspsp={"name": "mBank", "country": "PL"},
            psu_type="personal",
            access={"valid_until": (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()},
            accounts=[dict(uid="bank-uid", identification_hash="stable-hash", currency="PLN", account_id={"iban": iban})],
        ),
    )
    assert client.post(household["path"] + "/bank/connect").status_code == 200
    result = client.post("/bank/complete", json={"code": "authorization-code", "state": states[-1]})
    assert result.status_code == 200, result.text
    assert client.post("/bank/complete", json={"code": "authorization-code", "state": states[-1]}).status_code == 409
    with SessionLocal() as db:
        a = db.scalar(select(BankAccount))
        identifier = a.id
        assert "bank-uid" not in a.uid_cipher and "one-session" not in db.scalar(select(BankConnection)).session_cipher
        assert a.last4 == ("1234" if iban else "")
        assert bool(a.iban_hash) == bool(iban)
    assert client.post(household["path"] + "/bank/connect").status_code == 200
    assert client.post("/bank/complete", json={"code": "new-code", "state": states[-1]}).status_code == 200
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(BankAccount)) == 1 and db.scalar(select(BankAccount)).id == identifier
        assert "revoke_pending" in list(db.scalars(select(BankConnection.status)))


@pytest.mark.parametrize("value", ["NaN", "Infinity", "1.234", "1000000001.00"])
def test_exact_amount_validation(value):
    with pytest.raises(BankError):
        minor_amount(value)


@pytest.mark.parametrize("direction", ["DBIT", "CRDT"])
@pytest.mark.parametrize("shape", ["missing", "null", "empty", "null_values"])
def test_optional_transaction_fields_do_not_invent_data(direction, shape):
    side = "creditor" if direction == "DBIT" else "debtor"
    row = raw(direction=direction)
    for key in (side, side + "_account", "remittance_information"):
        row.pop(key, None)
    if shape == "null":
        row.update({side: None, side + "_account": None, "remittance_information": None})
    elif shape == "empty":
        row.update({side: {}, side + "_account": {}, "remittance_information": []})
    elif shape == "null_values":
        row.update({side: {"name": None}, side + "_account": {"iban": None}, "remittance_information": None})
    movement = bank_provider.movement(row, "PLN")
    assert movement["amount"] == (-1234 if direction == "DBIT" else 1234)
    assert movement["date"] == today()
    assert movement["reference"] == "ref-1"
    assert movement["description"] == "Operacja bankowa" and movement["counterparty_hash"] is None


@pytest.mark.parametrize(
    "change",
    [
        {"creditor": "not-an-object"},
        {"creditor": []},
        {"creditor": {"name": 123}},
        {"creditor_account": "not-an-object"},
        {"creditor_account": []},
        {"creditor_account": {"iban": 123}},
        {"creditor_account": {"iban": False}},
        {"remittance_information": {}},
        {"remittance_information": [None]},
        {"transaction_amount": None},
        {"booking_date": None},
        {"credit_debit_indicator": None},
        {"transaction_amount": {"currency": "PLN", "amount": "1.234"}},
    ],
)
def test_non_null_invalid_fields_still_fail_validation(change):
    with pytest.raises(BankError) as error:
        bank_provider.movement({**raw(), **change}, "PLN")
    assert error.value.code in ("INVALID_BANK_MOVEMENT", "INVALID_BANK_AMOUNT")


def test_optional_text_and_real_counterparty_identifier_are_preserved():
    movement = bank_provider.movement({**raw(creditor_account={"iban": "pl 00 1234"}), "remittance_information": "Koszyk"}, "PLN")
    assert movement["description"] == "Sklep QA · Koszyk"
    assert movement["counterparty_hash"] == bank_provider.digest("PL001234")


def test_realistic_nullable_batch_imports_once_without_duplicate_or_opening_balance_rewrite(client, household, configured, monkeypatch):
    connection, account = make_account(household, configured, initial=True)
    rows = [
        {**raw("debit", creditor_account={"iban": None}), "creditor": {"name": None}},
        {**raw("credit", direction="CRDT", debtor_account={"iban": None}), "debtor": None, "remittance_information": None},
    ]
    fake_feed(monkeypatch, rows)
    account_id = household["data"]["accounts"][0]["id"]
    initial_balance = household["data"]["accounts"][0]["balance"]
    assert bank_sync.sync_connection(configured, connection)
    assert not bank_sync.sync_connection(configured, connection)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(BankEntry)) == 2
        assert not db.scalar(select(Transaction))
        assert db.get(BankConnection, connection).error_code is None
        assert db.get(BankConnection, connection).last_sync is not None
        assert db.get(BankAccount, account).balance == 10000
        db.get(BankConnection, connection).next_sync = None
        db.commit()
    accounts = client.get(household["path"] + "/overview?month=2026-10").json()["accounts"]
    assert next(account["balance"] for account in accounts if account["id"] == account_id) == initial_balance
    assert bank_sync.sync_connection(configured, connection)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(BankEntry)) == 2 and not db.scalar(select(Transaction))


def test_malformed_optional_field_prevents_partial_batch_import(client, household, configured, monkeypatch):
    connection, _ = make_account(household, configured, initial=True)
    fake_feed(monkeypatch, [raw("valid", creditor_account={"iban": None}), raw("invalid", creditor_account={"iban": 123})])
    assert not bank_sync.sync_connection(configured, connection)
    with SessionLocal() as db:
        row = db.get(BankConnection, connection)
        assert row.error_code == "INVALID_BANK_MOVEMENT" and row.sync_diagnostic["stage"] == "parse_transactions"
        assert not db.scalar(select(BankEntry)) and not db.scalar(select(Transaction))


def test_pagination_stops_on_error_or_repeated_cursor(monkeypatch, configured):
    client = EnableBanking(configured)
    calls = []

    def request(method, path, data=None, params=None):
        calls.append(params)
        return {"transactions": [raw()], "continuation_key": "same"}

    monkeypatch.setattr(client, "call", request)
    with pytest.raises(BankError, match="PAGINATION_LOOP"):
        client.transactions("uid", today())
    assert len(calls) == 2


def test_push_keys_private_opt_in_outbox_and_expired_subscription(client, household, configured, monkeypatch):
    connection, _ = make_account(household, configured, initial=True)
    keys = {"auth": base64.urlsafe_b64encode(b"a" * 16).decode(), "p256dh": base64.urlsafe_b64encode(b"b" * 65).decode()}
    endpoint = "https://fcm.googleapis.com/fcm/send/secret-device-token"
    response = client.post(household["path"] + "/bank/subscriptions", json={"endpoint": endpoint, "keys": keys})
    assert response.status_code == 200, response.text
    assert (
        client.post(household["path"] + "/bank/subscriptions", json={"endpoint": "https://127.0.0.1/admin", "keys": keys}).status_code
        == 422
    )
    fake_feed(monkeypatch, [raw()])
    assert bank_sync.sync_connection(configured, connection)
    with SessionLocal() as db:
        assert endpoint not in db.scalar(select(BankSubscription)).payload_cipher
        assert db.scalar(select(func.count()).select_from(BankDelivery)) == 0
    fake_feed(monkeypatch, [raw(), raw("new", amount="2.00")])
    due(connection)
    assert bank_sync.sync_connection(configured, connection)
    sent = []

    def send(**kwargs):
        sent.append(kwargs)

    monkeypatch.setattr(bank_sync, "webpush", send)
    bank_sync.deliver(configured)
    bank_sync.deliver(configured)
    assert len(sent) == 1 and "Sklep" not in sent[0]["data"] and "12.34" not in sent[0]["data"]
    assert client.delete(household["path"] + "/bank/subscriptions/" + response.json()["id"]).status_code == 200


def test_household_deletion_blocked_until_disconnect(client, household, configured, monkeypatch):
    connection, _ = make_account(household, configured)
    assert client.request("DELETE", household["path"], json={"name": "Testowy dom"}).status_code == 409
    monkeypatch.setattr(EnableBanking, "revoke", lambda self, *args: {})
    assert client.delete(household["path"] + "/bank/connections/" + connection).status_code == 200
    assert client.request("DELETE", household["path"], json={"name": "Testowy dom"}).status_code == 200
    assert not Path(settings.bank_config_path).exists()
    assert not Path(configured.private_key_path).exists()


def test_bank_first_receipt_enriches_without_duplicate_and_protects_amount(client, household, configured, monkeypatch):
    connection, _ = make_account(household, configured)
    fake_feed(monkeypatch, [raw()])
    assert bank_sync.sync_connection(configured, connection)
    entry = client.get(household["path"] + "/bank").json()["entries"][0]
    tx = entry["transaction"]
    fixture = Path(__file__).resolve().parents[3] / "fixtures/lidl.png"
    receipt = client.post(
        household["path"] + "/receipts",
        files={"file": ("fixture.png", fixture.read_bytes(), "image/png")},
        headers={"Idempotency-Key": uuid4().hex},
    ).json()
    payload = {
        "merchant": "Bank test store",
        "date": today().isoformat(),
        "total": 1234,
        "account_id": household["data"]["accounts"][0]["id"],
        "acknowledge_duplicate": True,
        "items": [
            {
                "name": "Zakup QA",
                "amount": 1234,
                "category_id": household["data"]["categories"][0]["id"],
                "confidence": 100,
                "reviewed": True,
            }
        ],
        "target_transaction_id": tx["id"],
        "target_expected_updated_at": tx["updated_at"],
    }
    finalize = household["path"] + "/receipts/" + receipt["id"] + "/finalize"
    unlinked = {k: v for k, v in payload.items() if not k.startswith("target_")}
    assert client.post(finalize, json={**payload, "target_expected_updated_at": "2020-01-01T00:00:00Z"}).status_code == 409
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Transaction)) == 1
    response = client.post(finalize, json=unlinked)
    assert response.status_code == 200, response.text
    assert response.json()["id"] == tx["id"]
    assert client.post(household["path"] + "/receipts/" + receipt["id"] + "/finalize", json=payload).json()["id"] == tx["id"]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Transaction)) == 1
        assert db.get(Transaction, tx["id"]).status == "categorized"
        assert db.scalar(select(BankEntry)).reviewed
    tx = client.get(household["path"] + "/transactions/" + tx["id"]).json()
    edit = {
        "kind": "expense",
        "amount": 999,
        "date": today().isoformat(),
        "description": "Changed",
        "account_id": household["data"]["accounts"][0]["id"],
        "expected_updated_at": tx["updated_at"],
        "allocations": [{"category_id": household["data"]["categories"][0]["id"], "amount": 999}],
    }
    response = client.put(household["path"] + "/transactions/" + tx["id"], json=edit, headers={"Idempotency-Key": uuid4().hex})
    assert response.status_code == 422


def test_web_activation_reauthentication_exact_scope_and_no_key_replacement(client, household, configured, monkeypatch, tmp_path):
    owner = configured.owner_id
    with SessionLocal() as db:
        db.get(User, owner).is_admin = True
        db.commit()
    target = tmp_path / "activation" / "config.json"
    monkeypatch.setattr(settings, "bank_config_path", str(target))

    def application(self, method, path, **kwargs):
        return {"active": True, "environment": "PRODUCTION", "services": ["AIS"]}

    monkeypatch.setattr(EnableBanking, "call", application)
    data = {
        "app_id": str(uuid4()),
        "household_name": "Testowy dom",
        "password": "a-long-test-password",
        "private_key": Path(configured.private_key_path).read_text(),
        "confirm_share": True,
    }
    wrong = client.post(household["path"] + "/bank/activate", json={**data, "password": "wrong-password"})
    assert wrong.status_code == 403
    assert not target.exists()
    response = client.post(household["path"] + "/bank/activate", json=data)
    assert response.status_code == 200, response.text
    assert "PRIVATE KEY" not in response.text
    cfg = bank_provider.load_config()
    assert cfg.household_id == household["id"] and set(cfg.allowed_users) == set(configured.allowed_users)
    assert all(
        Path(path).stat().st_mode & 0o077 == 0 for path in [str(target), cfg.private_key_path, cfg.encryption_key_path, cfg.vapid_key_path]
    )
    assert client.post(household["path"] + "/bank/activate", json=data).status_code == 409


def test_sync_error_never_contains_provider_body_or_credentials(configured, monkeypatch):
    marker = "private-sensitive-bank-response"

    def response(*args, **kwargs):
        return httpx.Response(503, json={"error": {"message": marker}})

    monkeypatch.setattr(httpx, "request", response)
    with pytest.raises(BankError) as caught:
        EnableBanking(configured).call("GET", "/application")
    assert caught.value.code == "HTTP_503" and marker not in str(caught.value)


def test_unexpected_parse_failure_has_safe_durable_diagnostics_and_keeps_lease(client, household, configured, monkeypatch, caplog):
    connection, account = make_account(household, configured, initial=True)
    marker = "PRIVATE_TRANSACTION_IBAN_TOKEN"

    def request(self, *args, **kwargs):
        self.last_http_status = 200
        return {"transactions": [raw()]}

    def unexpected_parser_error(*args):
        raise AttributeError(marker)

    monkeypatch.setattr(EnableBanking, "call", request)
    monkeypatch.setattr(bank_sync, "movement", unexpected_parser_error)
    response = client.post(household["path"] + "/bank/sync")
    assert response.status_code == 200 and response.json()["failed"] == 1
    assert response.json()["synchronized"] == response.json()["waiting"] == 0
    assert "nie powiodła" in response.json()["message"]
    with SessionLocal() as db:
        row = db.get(BankConnection, connection)
        diagnostic = row.sync_diagnostic
        assert row.error_code == "SYNC_FAILED" and row.last_sync is None
        assert diagnostic["stage"] == "parse_transactions" and diagnostic["exception_type"] == "AttributeError"
        assert diagnostic["http_status"] == 200 and diagnostic["duration_ms"] >= 0
        assert datetime.fromisoformat(diagnostic["occurred_at"]).tzinfo is not None
        lease = row.next_sync
        assert lease > datetime.now(timezone.utc) + timedelta(hours=5)
        assert not db.scalar(select(BankEntry)) and not db.scalar(select(Transaction))
        assert db.get(BankAccount, account).last_sync is None
    state = client.get(household["path"] + "/bank").json()
    assert state["connections"][0]["sync_diagnostic"] == diagnostic
    assert state["connections"][0]["sync_available"] is False
    assert marker not in json.dumps(state) + caplog.text
    assert "stage=parse_transactions type=AttributeError code=SYNC_FAILED http_status=200" in caplog.text
    monkeypatch.setattr(EnableBanking, "transactions", lambda *args: pytest.fail("Retry must not bypass the lease"))
    waiting = client.post(household["path"] + "/bank/sync").json()
    assert waiting["waiting"] == 1 and waiting["failed"] == waiting["synchronized"] == 0
    assert "Nie rozpoczęto" in waiting["message"]
    with SessionLocal() as db:
        assert db.get(BankConnection, connection).next_sync == lease
        assert db.get(BankConnection, connection).sync_diagnostic == diagnostic


@pytest.mark.parametrize(
    "status,body,expected",
    [
        (503, {"error": "ASPSP_TIMEOUT"}, "ASPSP_TIMEOUT"),
        (429, {"error": "PRIVATE_SECRET_TOKEN"}, "HTTP_429"),
        (500, ["PRIVATE_SECRET_TOKEN"], "HTTP_500"),
        (200, ["PRIVATE_SECRET_TOKEN"], "INVALID_BANK_RESPONSE"),
        (200, {"transactions": None}, "INVALID_BANK_RESPONSE"),
        (200, {"transactions": [None]}, "INVALID_BANK_RESPONSE"),
        (200, {"transactions": [], "continuation_key": {"secret": "PRIVATE_SECRET_TOKEN"}}, "INVALID_BANK_RESPONSE"),
    ],
)
def test_provider_failures_store_http_status_without_response_content(
    client, household, configured, monkeypatch, caplog, status, body, expected
):
    connection, _ = make_account(household, configured, initial=True)
    monkeypatch.setattr(httpx, "request", lambda *args, **kwargs: httpx.Response(status, json=body))
    assert not bank_sync.sync_connection(configured, connection)
    with SessionLocal() as db:
        row = db.get(BankConnection, connection)
        assert row.error_code == expected
        assert row.sync_diagnostic["stage"] == "fetch_transactions"
        assert row.sync_diagnostic["http_status"] == status
        assert "PRIVATE_SECRET_TOKEN" not in json.dumps(row.sync_diagnostic) + caplog.text
        assert not db.scalar(select(BankEntry))


@pytest.mark.parametrize("kind,expected", [(httpx.ReadTimeout, "BANK_TIMEOUT"), (httpx.ConnectError, "BANK_UNAVAILABLE")])
def test_transport_failure_has_safe_type_without_private_url(client, household, configured, monkeypatch, caplog, kind, expected):
    connection, _ = make_account(household, configured, initial=True)

    def request(*args, **kwargs):
        raise kind("PRIVATE_URL_AND_SESSION_TOKEN")

    monkeypatch.setattr(httpx, "request", request)
    assert not bank_sync.sync_connection(configured, connection)
    state = client.get(household["path"] + "/bank").json()["connections"][0]
    assert state["error_code"] == expected and state["sync_diagnostic"]["http_status"] is None
    assert state["sync_diagnostic"]["exception_type"] in ("TimeoutException", "RequestError")
    assert "PRIVATE_URL_AND_SESSION_TOKEN" not in json.dumps(state) + caplog.text


def test_invalid_json_and_balances_are_diagnosed(configured, monkeypatch):
    monkeypatch.setattr(httpx, "request", lambda *args, **kwargs: httpx.Response(200, text="PRIVATE_NOT_JSON"))
    with pytest.raises(BankError) as error:
        EnableBanking(configured).call("GET", "/application")
    assert error.value.exception_type == "JSONDecodeError" and error.value.http_status == 200
    assert "PRIVATE_NOT_JSON" not in str(error.value)
    client = EnableBanking(configured)
    monkeypatch.setattr(client, "call", lambda *args: {"balances": [None]})
    with pytest.raises(BankError, match="INVALID_BANK_RESPONSE"):
        client.balances("private-account")


@pytest.mark.parametrize(
    "balances,stage,kind", [(None, "fetch_balances", "TypeError"), ([{"balance_type": "ITBD"}], "parse_balances", "KeyError")]
)
def test_balance_failure_preserves_entire_batch_and_reports_stage(client, household, configured, monkeypatch, balances, stage, kind):
    connection, _ = make_account(household, configured, initial=True)

    def request(self, method, path, *args, **kwargs):
        self.last_http_status = 200
        return {"transactions": [raw()]} if path.endswith("/transactions") else {"balances": balances}

    monkeypatch.setattr(EnableBanking, "call", request)
    assert not bank_sync.sync_connection(configured, connection)
    with SessionLocal() as db:
        diagnostic = db.get(BankConnection, connection).sync_diagnostic
        assert diagnostic["stage"] == stage and diagnostic["exception_type"] == kind and diagnostic["http_status"] == 200
        assert not db.scalar(select(BankEntry))


def test_bad_encrypted_identifier_is_diagnosed_without_leaking_it(client, household, configured, monkeypatch, caplog):
    connection, account = make_account(household, configured, initial=True)
    with SessionLocal() as db:
        db.get(BankAccount, account).uid_cipher = "PRIVATE_INVALID_CIPHERTEXT"
        db.commit()
    monkeypatch.setattr(EnableBanking, "transactions", lambda *args: pytest.fail("Decryption failure must not contact the provider"))
    assert not bank_sync.sync_connection(configured, connection)
    with SessionLocal() as db:
        diagnostic = db.get(BankConnection, connection).sync_diagnostic
        assert diagnostic["stage"] == "decrypt_account" and diagnostic["exception_type"] == "InvalidToken"
        assert diagnostic["http_status"] is None
        assert "PRIVATE_INVALID_CIPHERTEXT" not in json.dumps(diagnostic) + caplog.text


def test_database_failure_rolls_back_whole_batch_and_persists_diagnostic(client, household, configured, monkeypatch, caplog):
    connection, account = make_account(household, configured, initial=True)
    fake_feed(monkeypatch, [raw()])

    def audit_failure(db, *args):
        db.execute(text("SELECT CAST('PRIVATE_DATABASE_VALUE' AS integer)"))

    monkeypatch.setattr(bank_sync, "audit", audit_failure)
    assert not bank_sync.sync_connection(configured, connection)
    with SessionLocal() as db:
        row = db.get(BankConnection, connection)
        assert row.sync_diagnostic["stage"] == "commit" and row.sync_diagnostic["exception_type"] == "DatabaseError"
        assert row.sync_diagnostic["http_status"] is None and row.last_sync is None
        assert row.next_sync > datetime.now(timezone.utc)
        assert not db.scalar(select(BankEntry)) and not db.scalar(select(Transaction))
        assert db.get(BankAccount, account).last_sync is None and db.get(BankAccount, account).balance is None
        assert "PRIVATE_DATABASE_VALUE" not in caplog.text + json.dumps(row.sync_diagnostic)


def test_success_clears_diagnostics_and_unmapped_accounts_do_not_take_lease(client, household, configured, monkeypatch):
    connection, account = make_account(household, configured, initial=True)
    with SessionLocal() as db:
        row = db.get(BankAccount, account)
        mapped = row.account_id
        row.account_id = None
        db.commit()
    monkeypatch.setattr(EnableBanking, "transactions", lambda *args: pytest.fail("Unmapped account must not fetch"))
    result = client.post(household["path"] + "/bank/sync").json()
    assert result["unmapped"] == 1 and "przypisz" in result["message"]
    with SessionLocal() as db:
        assert db.get(BankConnection, connection).next_sync is None
        db.get(BankAccount, account).account_id = mapped
        db.get(BankConnection, connection).error_code = "SYNC_FAILED"
        db.get(BankConnection, connection).sync_diagnostic = {"legacy": True}
        db.commit()
    fake_feed(monkeypatch, [raw()])
    result = client.post(household["path"] + "/bank/sync").json()
    assert result["synchronized"] == 1 and result["failed"] == 0
    with SessionLocal() as db:
        row = db.get(BankConnection, connection)
        assert row.last_sync is not None and row.error_code is None and row.sync_diagnostic is None
        assert db.scalar(select(func.count()).select_from(BankEntry)) == 1


def test_diagnostic_allowlist_rejects_custom_exception_names_and_extra_fields():
    from app.bank_diagnostics import failure_diagnostic, public_diagnostic

    error = type("PRIVATE_CUSTOM_EXCEPTION_NAME", (Exception,), {})("PRIVATE_EXCEPTION_MESSAGE")
    diagnostic = failure_diagnostic(error, "fetch_transactions", 1, 200)
    assert diagnostic["exception_type"] == "UnexpectedError"
    assert "PRIVATE" not in json.dumps(diagnostic)
    assert public_diagnostic({**diagnostic, "payload": "PRIVATE_PAYLOAD"}) == diagnostic
    assert public_diagnostic({**diagnostic, "exception_type": "PRIVATE_CUSTOM_EXCEPTION_NAME"}) is None
    assert public_diagnostic({**diagnostic, "code": "PRIVATE_PROVIDER_CODE"})["code"] == "SYNC_FAILED"


def test_diagnostic_migration_preserves_connection_and_refuses_history_loss(client, household, configured):
    import os
    import subprocess
    import sys
    from app.db import engine

    connection, _ = make_account(household, configured, initial=True)
    env = {**os.environ, "DATABASE_URL": engine.url.render_as_string(hide_password=False)}

    def migrate(*args):
        return subprocess.run(
            [sys.executable, "-m", "alembic", *args], cwd=Path(__file__).resolve().parents[1], env=env, capture_output=True
        )

    assert migrate("downgrade", "015").returncode == 0
    try:
        assert migrate("upgrade", "head").returncode == 0
        with SessionLocal() as db:
            row = db.get(BankConnection, connection)
            assert configured.open(row.session_cipher) == "private-session" and row.sync_diagnostic is None
            row.sync_diagnostic = {"stage": "fetch_transactions"}
            db.commit()
        assert migrate("downgrade", "015").returncode != 0
        with SessionLocal() as db:
            assert db.get(BankConnection, connection).sync_diagnostic == {"stage": "fetch_transactions"}
    finally:
        assert migrate("upgrade", "head").returncode == 0


def test_sync_lease_reentry_and_membership_change_during_unlocked_http(client, household, configured, monkeypatch):
    connection, _ = make_account(household, configured)
    fake_feed(monkeypatch, [])

    def fetch(self, *args):
        # A second process sees the persisted lease, and the family remains writable
        # while the first request waits for the provider.
        assert not bank_sync.sync_connection(configured, connection)
        with SessionLocal() as concurrent:
            assert concurrent.scalar(select(Household).where(Household.id == household["id"]).with_for_update(nowait=True))
            concurrent.execute(delete(Member).where(Member.household_id == household["id"], Member.user_id == configured.owner_id))
            concurrent.commit()
        return [raw()]

    monkeypatch.setattr(EnableBanking, "transactions", fetch)
    assert not bank_sync.sync_connection(configured, connection)
    with SessionLocal() as db:
        assert db.get(BankConnection, connection).status == "revoke_pending"
        assert not db.scalar(select(BankEntry)) and not db.scalar(select(Transaction))


def test_own_transfer_links_both_legs_once_and_description_preserves_kind(client, household, configured, monkeypatch):
    connection, first = make_account(household, configured)
    other = client.post(
        household["path"] + "/accounts",
        json={"name": "Drugie konto bankowe", "kind": "checking", "currency": "PLN", "opening_balance": 0},
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert other.status_code == 201, other.text
    with SessionLocal() as db:
        second = BankAccount(
            household_id=household["id"],
            connection_id=connection,
            uid_cipher=configured.seal("second"),
            identity_hash="b" * 64,
            last4="4321",
            currency="PLN",
            account_id=other.json()["id"],
            start_date=today(),
            iban_hash=bank_provider.digest("PL" + "1" * 26),
        )
        db.add(second)
        db.commit()

    fake_feed(monkeypatch, [])
    monkeypatch.setattr(
        EnableBanking,
        "transactions",
        lambda self, uid, start: [
            raw("own-debit", creditor_account={"iban": "PL" + "1" * 26}) if uid != "second" else raw("own-credit", direction="CRDT")
        ],
    )
    assert bank_sync.sync_connection(configured, connection)
    path = household["path"] + "/bank"
    entries = client.get(path).json()["entries"]
    debit = next(e for e in entries if e["amount"] < 0)
    credit = next(e for e in entries if e["amount"] > 0)
    assert not debit["transaction"] and not credit["transaction"]
    response = client.post(
        path + "/entries/" + debit["id"] + "/resolve",
        json={
            "action": "transfer",
            "expected_updated_at": debit["updated_at"],
            "description": "Przelew między naszymi kontami",
            "destination_id": other.json()["id"],
        },
    )
    assert response.status_code == 200, response.text
    entries = client.get(path).json()["entries"]
    debit = next(e for e in entries if e["amount"] < 0)
    credit = next(e for e in entries if e["amount"] > 0)
    assert len(credit["candidates"]) == 1
    tx = debit["transaction"]
    assert (
        client.post(
            path + "/entries/" + credit["id"] + "/resolve",
            json={
                "action": "match",
                "expected_updated_at": credit["updated_at"],
                "description": "Wpływ własny",
                "transaction_id": tx["id"],
            },
        ).status_code
        == 200
    )
    assert (
        client.post(
            path + "/entries/" + debit["id"] + "/resolve",
            json={
                "action": "describe",
                "expected_updated_at": debit["updated_at"],
                "expected_transaction_updated_at": tx["updated_at"],
                "description": "Zmieniony opis przelewu",
            },
        ).status_code
        == 200
    )
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Transaction)) == 1
        assert db.get(Transaction, tx["id"]).kind == "transfer"
        assert db.get(Transaction, tx["id"]).destination_id == other.json()["id"]
        assert {e.transaction_id for e in db.scalars(select(BankEntry))} == {tx["id"]}


def test_describe_preserves_existing_expense_allocations(client, household, configured, monkeypatch):
    connection, _ = make_account(household, configured)
    fake_feed(monkeypatch, [raw()])
    assert bank_sync.sync_connection(configured, connection)
    path = household["path"] + "/bank"
    entry = client.get(path).json()["entries"][0]
    tx = entry["transaction"]
    split = {"category_id": household["data"]["categories"][0]["id"], "amount": 1234}
    assert (
        client.post(
            path + "/entries/" + entry["id"] + "/resolve",
            json={
                "action": "describe",
                "expected_updated_at": entry["updated_at"],
                "expected_transaction_updated_at": tx["updated_at"],
                "description": "Opis i kategoria",
                "allocations": [split],
            },
        ).status_code
        == 200
    )
    entry = client.get(path).json()["entries"][0]
    tx = entry["transaction"]
    assert (
        client.post(
            path + "/entries/" + entry["id"] + "/resolve",
            json={
                "action": "describe",
                "expected_updated_at": entry["updated_at"],
                "expected_transaction_updated_at": tx["updated_at"],
                "description": "Sam opis",
            },
        ).status_code
        == 200
    )
    with SessionLocal() as db:
        assert db.get(Transaction, tx["id"]).status == "categorized"
        assert db.scalar(select(TransactionAllocation)).amount == 1234


def test_expired_device_with_multiple_queued_messages_does_not_rollback_cleanup(client, household, configured, monkeypatch):
    connection, _ = make_account(household, configured)
    keys = {"auth": base64.urlsafe_b64encode(b"a" * 16).decode(), "p256dh": base64.urlsafe_b64encode(b"b" * 65).decode()}
    assert (
        client.post(
            household["path"] + "/bank/subscriptions",
            json={
                "endpoint": "https://web.push.apple.com/qa-device",
                "keys": keys,
            },
        ).status_code
        == 200
    )
    fake_feed(monkeypatch, [])
    assert bank_sync.sync_connection(configured, connection)
    fake_feed(monkeypatch, [raw("new-1"), raw("new-2", amount="2.00")])
    due(connection)
    assert bank_sync.sync_connection(configured, connection)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(BankDelivery)) == 2
    sent = []

    def expired(**kwargs):
        sent.append(True)
        raise bank_sync.WebPushException("Gone", response=httpx.Response(410))

    monkeypatch.setattr(bank_sync, "webpush", expired)
    bank_sync.deliver(configured)
    assert len(sent) == 1
    with SessionLocal() as db:
        assert not db.scalar(select(BankSubscription))
        assert not db.scalar(select(BankDelivery))


def test_first_import_is_baseline_and_only_future_new_expenses_book_automatically(client, household, configured, monkeypatch):
    connection, _ = make_account(household, configured, initial=True)
    fake_feed(monkeypatch, [raw("already-in-starting-balance")])
    assert bank_sync.sync_connection(configured, connection)
    with SessionLocal() as db:
        assert db.scalar(select(BankEntry)).transaction_id is None
        assert db.scalar(select(func.count()).select_from(Transaction)) == 0
    fake_feed(monkeypatch, [raw("already-in-starting-balance"), raw("new-after-baseline", amount="2.00")])
    due(connection)
    assert bank_sync.sync_connection(configured, connection)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Transaction)) == 1
        assert db.scalar(select(Transaction)).amount == 200
        assert db.scalar(select(func.count()).select_from(BankEntry)) == 2


def test_single_bank_pair_in_reverse_order_and_placeholder_merge(client, household, configured, monkeypatch):
    connection, _ = make_account(household, configured)
    fake_feed(monkeypatch, [raw()])
    assert bank_sync.sync_connection(configured, connection)
    before = client.get(household["path"] + "/bank").json()["entries"][0]
    assert before["transaction"]
    account = household["data"]["accounts"][0]["id"]
    tx = client.post(
        household["path"] + "/transactions",
        json={
            "kind": "expense",
            "amount": 1234,
            "date": today().isoformat(),
            "account_id": account,
            "description": "Paragon dodany później",
        },
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert tx.status_code == 201, tx.text
    entry = client.get(household["path"] + "/bank").json()["entries"][0]
    assert entry["transaction"]["id"] == tx.json()["id"] and entry["match_method"] == "unique"
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Transaction)) == 1
        assert not db.get(Transaction, before["transaction"]["id"])


@pytest.mark.parametrize("two_bank_entries", [False, True])
def test_ambiguous_graph_never_picks_arbitrary_matching_pair(client, household, configured, monkeypatch, two_bank_entries):
    account = household["data"]["accounts"][0]["id"]
    for index in range(1 if two_bank_entries else 2):
        assert (
            client.post(
                household["path"] + "/transactions",
                json={
                    "kind": "expense",
                    "amount": 1234,
                    "date": today().isoformat(),
                    "account_id": account,
                    "description": "Równy zakup " + str(index),
                },
                headers={"Idempotency-Key": uuid4().hex},
            ).status_code
            == 201
        )
    connection, _ = make_account(household, configured)
    fake_feed(monkeypatch, [raw("one"), raw("two")] if two_bank_entries else [raw()])
    assert bank_sync.sync_connection(configured, connection)
    entries = client.get(household["path"] + "/bank").json()["entries"]
    assert all(e["transaction"] is None and not e["reviewed"] for e in entries)


def test_real_credit_becomes_unique_refund_and_is_not_income(client, household, configured, monkeypatch):
    account = household["data"]["accounts"][0]["id"]
    category = household["data"]["categories"][0]["id"]
    original = client.post(
        household["path"] + "/transactions",
        json={
            "kind": "expense",
            "amount": 24999,
            "date": today().isoformat(),
            "account_id": account,
            "description": "CALZEDONIA",
            "allocations": [{"category_id": category, "amount": 24999}],
        },
        headers={"Idempotency-Key": uuid4().hex},
    ).json()
    connection, _ = make_account(household, configured)
    debit = raw("purchase", amount="249.99")
    debit["creditor"] = {"name": "CALZEDONIA"}
    fake_feed(monkeypatch, [debit])
    assert bank_sync.sync_connection(configured, connection)
    credit = raw("return", amount="249.99", direction="CRDT")
    credit["debtor"] = {"name": "CALZEDONIA"}
    credit["remittance_information"] = ["ZWROT BLIK"]
    due(connection)
    fake_feed(monkeypatch, [debit, credit])
    assert bank_sync.sync_connection(configured, connection)
    status = client.get(household["path"] + "/bank").json()
    returned = next(e for e in status["entries"] if e["amount"] > 0)
    assert (
        returned["reviewed"] and returned["transaction"]["kind"] == "refund" and returned["transaction"]["refund_of_id"] == original["id"]
    )
    assert returned["match_method"] == "refund"
    budget = client.get(household["path"] + "/overview?month=" + today().strftime("%Y-%m")).json()["budget"]
    assert budget["income"] == 0 and budget["expenses"] == 0 and budget["refunds"] == 24999
    due(connection)
    assert bank_sync.sync_connection(configured, connection)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Transaction)) == 2
    result = client.post(
        household["path"] + "/bank/entries/" + returned["id"] + "/resolve",
        json={
            "action": "income",
            "description": "Jednak zwykły wpływ",
            "expected_updated_at": returned["updated_at"],
            "expected_transaction_updated_at": returned["transaction"]["updated_at"],
        },
    )
    assert result.status_code == 200, result.text
    budget = client.get(household["path"] + "/overview?month=" + today().strftime("%Y-%m")).json()["budget"]
    assert budget["income"] == 24999 and budget["expenses"] == 24999 and budget["refunds"] == 0


def test_equal_debits_and_unrelated_salary_are_never_automatic_refunds(client, household, configured, monkeypatch):
    connection, _ = make_account(household, configured)
    debit = raw("one", amount="249.99")
    debit["creditor"] = {"name": "CALZEDONIA"}
    fake_feed(monkeypatch, [debit])
    assert bank_sync.sync_connection(configured, connection)
    debit2 = {**debit, "entry_reference": "two"}
    salary = raw("salary", amount="249.99", direction="CRDT")
    salary["debtor"] = {"name": "Pracodawca Inna Firma"}
    fake_feed(monkeypatch, [debit, debit2, salary])
    due(connection)
    assert bank_sync.sync_connection(configured, connection)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Transaction).where(Transaction.refund_of_id.is_not(None))) == 0
        assert db.scalar(select(func.count()).select_from(Transaction).where(Transaction.kind == "expense")) == 2


def test_balance_alignment_is_exact_idempotent_and_not_a_budget_movement(client, household, configured):
    from app.models import Account, AccountAdjustment

    _, bank_id = make_account(household, configured)
    moment = datetime.now(timezone.utc)
    with SessionLocal() as db:
        bank = db.get(BankAccount, bank_id)
        bank.balance = 158353
        bank.balance_at = moment
        db.get(Account, bank.account_id).opening_balance = 510157
        db.commit()
    data = {"expected_app_balance": 510157, "expected_bank_balance": 158353, "expected_bank_balance_at": moment.isoformat()}
    path = household["path"] + "/bank/accounts/" + bank_id + "/align"
    key = uuid4().hex
    first = client.post(path, json=data, headers={"Idempotency-Key": key})
    assert first.status_code == 200, first.text
    assert first.json()["amount"] == -351804 and first.json()["balance_after"] == 158353
    assert client.post(path, json=data, headers={"Idempotency-Key": key}).json()["id"] == first.json()["id"]
    assert client.post(path, json=data, headers={"Idempotency-Key": uuid4().hex}).status_code == 409
    overview = client.get(household["path"] + "/overview?month=" + today().strftime("%Y-%m")).json()
    assert overview["accounts"][0]["balance"] == 158353 and overview["budget"]["income"] == 0 and overview["budget"]["expenses"] == 0
    status = client.get(household["path"] + "/bank").json()
    assert status["accounts"][0]["difference"] == 0 and status["accounts"][0]["adjustments"][0]["created_by_name"] == "Roch"
    exported = client.get(household["path"] + "/export").json()
    assert exported["account_adjustments"][0]["amount"] == -351804
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(AccountAdjustment)) == 1
        member = db.scalar(select(Member).where(Member.household_id == household["id"], Member.user_id == configured.owner_id))
        member.role = "member"
        db.commit()
    assert client.post(path, json=data, headers={"Idempotency-Key": uuid4().hex}).status_code == 403


def test_two_equal_refund_credits_competing_for_one_purchase_stay_unresolved(client, household, configured, monkeypatch):
    account = household["data"]["accounts"][0]["id"]
    original = client.post(
        household["path"] + "/transactions",
        json={"kind": "expense", "amount": 1234, "date": today().isoformat(), "account_id": account, "description": "CALZEDONIA"},
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert original.status_code == 201
    connection, _ = make_account(household, configured)
    credits = [raw("return-" + str(i), direction="CRDT") for i in range(2)]
    for r in credits:
        r["debtor"] = {"name": "CALZEDONIA"}
        r["remittance_information"] = ["ZWROT"]
    fake_feed(monkeypatch, credits)
    assert bank_sync.sync_connection(configured, connection)
    entries = client.get(household["path"] + "/bank").json()["entries"]
    assert all(e["transaction"] is None for e in entries)


def test_explicit_separate_receipt_is_not_later_merged_by_automation(client, household, configured, monkeypatch):
    connection, _ = make_account(household, configured)
    fake_feed(monkeypatch, [raw()])
    assert bank_sync.sync_connection(configured, connection)
    bank_id = client.get(household["path"] + "/bank").json()["entries"][0]["transaction"]["id"]
    fixture = Path(__file__).resolve().parents[3] / "fixtures/lidl.png"
    receipt = client.post(
        household["path"] + "/receipts",
        files={"file": ("receipt.png", fixture.read_bytes(), "image/png")},
        headers={"Idempotency-Key": uuid4().hex},
    ).json()
    data = {
        "merchant": "Inny zakup",
        "date": today().isoformat(),
        "total": 1234,
        "account_id": household["data"]["accounts"][0]["id"],
        "acknowledge_bank_separate": True,
        "items": [
            {
                "name": "Inny zakup",
                "amount": 1234,
                "category_id": household["data"]["categories"][0]["id"],
                "confidence": 100,
                "reviewed": True,
            }
        ],
    }
    response = client.post(household["path"] + "/receipts/" + receipt["id"] + "/finalize", json=data)
    assert response.status_code == 200, response.text
    assert response.json()["id"] != bank_id
    assert client.post(household["path"] + "/bank/reconcile").status_code == 200
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Transaction)) == 2
        assert db.get(Transaction, response.json()["id"]).bank_match_excluded
        assert db.scalar(select(BankEntry)).transaction_id == bank_id


def test_alignment_rejects_new_bank_snapshot_before_any_balance_change(client, household, configured):
    from app.models import AccountAdjustment

    _, bid = make_account(household, configured)
    moment = datetime.now(timezone.utc)
    with SessionLocal() as db:
        bank = db.get(BankAccount, bid)
        bank.balance = 10000
        bank.balance_at = moment
        db.commit()
    body = {"expected_app_balance": 0, "expected_bank_balance": 10000, "expected_bank_balance_at": moment.isoformat()}
    with SessionLocal() as db:
        bank = db.get(BankAccount, bid)
        bank.balance = 9000
        bank.balance_at = moment + timedelta(seconds=1)
        db.commit()
    response = client.post(household["path"] + "/bank/accounts/" + bid + "/align", json=body, headers={"Idempotency-Key": uuid4().hex})
    assert response.status_code == 409
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(AccountAdjustment)) == 0


def test_legacy_bank_income_is_reclassified_as_refund_without_recording_cash_twice(client, household, configured, monkeypatch):
    account = household["data"]["accounts"][0]["id"]
    original = client.post(
        household["path"] + "/transactions",
        json={
            "kind": "expense",
            "amount": 1234,
            "date": today().isoformat(),
            "account_id": account,
            "description": "Lidl",
            "allocations": [{"category_id": household["data"]["categories"][0]["id"], "amount": 1234}],
        },
        headers={"Idempotency-Key": uuid4().hex},
    ).json()
    connection, _ = make_account(household, configured, initial=True)
    credit = raw("legacy-return", direction="CRDT")
    credit["debtor"] = {"name": "LIDL"}
    credit["remittance_information"] = ["ZWROT"]
    fake_feed(monkeypatch, [credit])
    assert bank_sync.sync_connection(configured, connection)
    entry = client.get(household["path"] + "/bank").json()["entries"][0]
    # Reproduce the old version's recorded bank income (not a new explicit decision).
    from app.domain import create_transaction
    from app.schemas import TransactionInput

    with SessionLocal() as db:
        member = db.scalar(select(Member).where(Member.household_id == household["id"], Member.user_id == configured.owner_id))
        income = create_transaction(
            db,
            member,
            TransactionInput(kind="income", amount=1234, date=today(), account_id=account, description="LIDL ZWROT"),
            "legacy-income-idempotency",
            source="bank",
            source_id=entry["id"],
        )
        record = db.get(BankEntry, entry["id"])
        record.transaction_id = income.id
        record.reviewed = True
        record.match_method = None
        income_id = income.id
        db.commit()
    before = client.get(household["path"] + "/overview?month=" + today().strftime("%Y-%m")).json()
    result = client.post(household["path"] + "/bank/reconcile")
    assert result.status_code == 200, result.text
    assert result.json()["refunds"] == 1
    after = client.get(household["path"] + "/overview?month=" + today().strftime("%Y-%m")).json()
    assert after["accounts"][0]["balance"] == before["accounts"][0]["balance"] == 0
    assert after["budget"]["income"] == 0 and after["budget"]["expenses"] == 0
    record = client.get(household["path"] + "/bank").json()["entries"][0]
    assert record["transaction"]["id"] == income_id and record["transaction"]["refund_of_id"] == original["id"]


def test_concurrent_alignment_only_posts_one_correction(client, household, configured):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from app.models import AccountAdjustment

    _, bid = make_account(household, configured)
    moment = datetime.now(timezone.utc)
    with SessionLocal() as db:
        bank = db.get(BankAccount, bid)
        bank.balance = 10000
        bank.balance_at = moment
        db.commit()
    data = {"expected_app_balance": 0, "expected_bank_balance": 10000, "expected_bank_balance_at": moment.isoformat()}
    ready = Barrier(2)

    def write(index):
        ready.wait(timeout=10)
        return client.post(
            household["path"] + "/bank/accounts/" + bid + "/align", json=data, headers={"Idempotency-Key": uuid4().hex}
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(write, range(2)))
    assert sorted(statuses) == [200, 409]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(AccountAdjustment)) == 1
