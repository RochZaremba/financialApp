import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select, func

from app import recovery
from app.db import SessionLocal
from app.main import app
from app.models import PasswordResetEvent, RecoveryGrantUse, SessionToken, User
from app.security import digest

EMAIL = "kaja@example.com"
OLD = "old-test-password"
NEW = " new-test-password "


def issue(monkeypatch, email=EMAIL, offset=timedelta(0)):
    private = Ed25519PrivateKey.generate()
    now = datetime.now(timezone.utc) + offset
    grant = recovery.Grant(
        id=uuid4().hex,
        target_email_sha256=digest(email),
        public_key=base64.urlsafe_b64encode(private.public_key().public_bytes_raw()).decode().rstrip("="),
        valid_from=now - timedelta(minutes=5),
        expires_at=now + timedelta(hours=1),
    )
    token = grant.id + "." + base64.urlsafe_b64encode(private.sign(recovery.message(grant))).decode().rstrip("=")
    monkeypatch.setattr(recovery, "GRANTS", [grant])
    return grant, {"email": email, "key": token, "password": NEW, "password_confirmation": NEW}


def register(client, email=EMAIL):
    assert client.post("/auth/register", json={"email": email, "password": OLD}).status_code == 201


def test_scoped_reset_revokes_all_sessions_and_is_durably_single_use(client, monkeypatch):
    register(client)
    cookie = client.cookies.get("dom_session")
    client.post("/auth/login", json={"email": EMAIL, "password": OLD})
    grant, payload = issue(monkeypatch)
    assert client.post("/auth/recover", json=payload).status_code == 200
    assert client.get("/auth/me").status_code == 401
    client.cookies.set("dom_session", cookie)
    assert client.get("/auth/me").status_code == 401
    assert client.post("/auth/login", json={"email": EMAIL, "password": OLD}).status_code == 401
    assert client.post("/auth/login", json={"email": EMAIL, "password": NEW}).status_code == 200
    assert client.post("/auth/recover", json=payload).status_code == 400
    with SessionLocal() as db:
        assert db.get(RecoveryGrantUse, grant.id)
        assert db.scalar(select(func.count()).select_from(PasswordResetEvent)) == 1
        assert db.scalar(select(func.count()).select_from(SessionToken)) == 1


@pytest.mark.parametrize("offset", [timedelta(hours=-2), timedelta(hours=2)])
def test_expired_and_not_yet_valid_grants_preserve_password(client, monkeypatch, offset):
    register(client)
    _, payload = issue(monkeypatch, offset=offset)
    assert client.post("/auth/recover", json=payload).status_code == 400
    assert client.post("/auth/login", json={"email": EMAIL, "password": OLD}).status_code == 200


@pytest.mark.parametrize("kind", ["wrong_email", "unknown_grant", "bad_signature", "invalid_encoding", "extended_expiry", "empty_config"])
def test_invalid_grants_cannot_change_any_account(client, monkeypatch, kind):
    register(client)
    register(client, "other@example.com")
    grant, payload = issue(monkeypatch)
    if kind == "wrong_email":
        payload["email"] = "other@example.com"
    elif kind == "unknown_grant":
        payload["key"] = uuid4().hex + payload["key"][32:]
    elif kind == "bad_signature":
        payload["key"] = grant.id + "." + "a" * 86
    elif kind == "invalid_encoding":
        payload["key"] = grant.id + "." + "!" * 86
    elif kind == "extended_expiry":
        grant.expires_at += timedelta(minutes=1)
    else:
        monkeypatch.setattr(recovery, "GRANTS", [])
    response = client.post("/auth/recover", json=payload)
    assert response.status_code == 400
    assert response.json() == {"detail": recovery.INVALID}
    assert client.post("/auth/login", json={"email": EMAIL, "password": OLD}).status_code == 200
    assert client.post("/auth/login", json={"email": "other@example.com", "password": OLD}).status_code == 200
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(RecoveryGrantUse)) == 0


def test_missing_account_and_administrator_are_rejected_identically(client, monkeypatch):
    _, payload = issue(monkeypatch)
    missing = client.post("/auth/recover", json=payload)
    register(client)
    with SessionLocal() as db:
        db.scalar(select(User).where(User.email == EMAIL)).is_admin = True
        db.commit()
    admin = client.post("/auth/recover", json=payload)
    assert admin.status_code == missing.status_code == 400
    assert admin.json() == missing.json() == {"detail": recovery.INVALID}


def test_success_clears_unrelated_browser_cookie_without_changing_its_account(client, monkeypatch):
    register(client)
    register(client, "helper@example.com")
    _, payload = issue(monkeypatch)
    response = client.post("/auth/recover", json=payload)
    assert response.status_code == 200 and "Max-Age=0" in response.headers["set-cookie"]
    assert client.get("/auth/me").status_code == 401
    assert client.post("/auth/login", json={"email": "helper@example.com", "password": OLD}).status_code == 200


def test_confirmation_validation_and_csrf_do_not_consume_grant(client, monkeypatch):
    register(client)
    _, payload = issue(monkeypatch)
    assert client.post("/auth/recover", json=payload, headers={"Origin": "https://evil.example"}).status_code == 403
    invalid = dict(payload, password_confirmation="a-different-password")
    response = client.post("/auth/recover", json=invalid)
    assert response.status_code == 422
    assert NEW not in response.text and payload["key"] not in response.text
    assert client.post("/auth/recover", json=dict(payload, is_admin=True)).status_code == 422
    assert client.post("/auth/recover", json=payload).status_code == 200


def test_recovery_rate_limit(client, monkeypatch):
    _, payload = issue(monkeypatch)
    for _ in range(5):
        assert client.post("/auth/recover", json=payload).status_code == 400
    response = client.post("/auth/recover", json=payload)
    assert response.status_code == 429 and response.headers["Retry-After"] == "300"


def test_concurrent_uses_only_one_password_can_win(client, monkeypatch):
    register(client)
    _, payload = issue(monkeypatch)

    def attempt(password):
        with TestClient(app) as contender:
            result = contender.post("/auth/recover", json=dict(payload, password=password, password_confirmation=password))
            return password, result.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, ["winning-password-one", "winning-password-two"]))
    assert sorted(status for _, status in outcomes) == [200, 400]
    for password, status in outcomes:
        login = client.post("/auth/login", json={"email": EMAIL, "password": password})
        assert login.status_code == (200 if status == 200 else 401)


def test_consumed_nonce_survives_account_deletion(client, monkeypatch):
    register(client)
    grant, payload = issue(monkeypatch)
    assert client.post("/auth/recover", json=payload).status_code == 200
    with SessionLocal() as db:
        db.delete(db.scalar(select(User).where(User.email == EMAIL)))
        db.commit()
        assert db.get(RecoveryGrantUse, grant.id).target_id is None
    register(client)
    assert client.post("/auth/recover", json=payload).status_code == 400


def test_grants_require_short_explicit_absolute_deadlines(monkeypatch):
    grant, _ = issue(monkeypatch)
    for changes in [
        {"expires_at": grant.valid_from + timedelta(hours=25)},
        {"expires_at": grant.valid_from},
        {"valid_from": grant.valid_from.replace(tzinfo=None)},
    ]:
        with pytest.raises(ValidationError):
            recovery.Grant.model_validate(grant.model_dump() | changes)
