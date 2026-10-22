import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import PasswordResetEvent, User

ADMIN_PASSWORD = "administrator-test-password"
OLD_PASSWORD = "ordinary-user-password"
NEW_PASSWORD = "  new-user-password  "


def register(client, email, password=OLD_PASSWORD):
    response = client.post("/auth/register", json={"email": email, "password": password})
    assert response.status_code == 201
    return response.json()["id"]


@pytest.fixture
def admin(client):
    identifier = register(client, "admin@example.com", ADMIN_PASSWORD)
    with SessionLocal() as db:
        db.get(User, identifier).is_admin = True
        db.commit()
    return identifier


def payload(**overrides):
    return {"email": "person@example.com", "password": NEW_PASSWORD, "admin_password": ADMIN_PASSWORD, **overrides}


def test_reset_requires_admin_and_cannot_be_granted_through_registration(client):
    assert client.post("/admin/password-reset", json=payload()).status_code == 401
    assert (
        client.post("/auth/register", json={"email": "admin@example.com", "password": ADMIN_PASSWORD, "is_admin": True}).status_code == 422
    )
    register(client, "person@example.com")
    assert client.get("/auth/me").json()["user"]["is_admin"] is False
    assert client.post("/admin/password-reset", json=payload()).status_code == 403
    with SessionLocal() as db:
        assert not db.scalars(select(PasswordResetEvent)).all()


def test_admin_reset_revokes_all_sessions_and_keeps_admin_logged_in(client, admin):
    with TestClient(app) as first, TestClient(app) as second:
        target = register(first, "person@example.com")
        assert second.post("/auth/login", json={"email": "person@example.com", "password": OLD_PASSWORD}).status_code == 200
        assert client.get("/auth/me").json()["user"]["is_admin"] is True
        result = client.post("/admin/password-reset", json=payload(email="PERSON@EXAMPLE.COM"))
        assert result.status_code == 200 and result.json() == {"ok": True}
        assert NEW_PASSWORD not in result.text and ADMIN_PASSWORD not in result.text
        assert first.get("/auth/me").status_code == second.get("/auth/me").status_code == 401
        assert client.get("/auth/me").status_code == 200
        assert first.post("/auth/login", json={"email": "person@example.com", "password": OLD_PASSWORD}).status_code == 401
        # Leading and trailing spaces remain part of the new password.
        assert first.post("/auth/login", json={"email": "person@example.com", "password": NEW_PASSWORD.strip()}).status_code == 401
        assert first.post("/auth/login", json={"email": "person@example.com", "password": NEW_PASSWORD}).status_code == 200
        with SessionLocal() as db:
            events = db.scalars(select(PasswordResetEvent)).all()
            assert len(events) == 1 and events[0].actor_id == admin and events[0].target_id == target
            assert db.get(User, target).updated_by == admin


def test_admin_reauthentication_validation_and_csrf(client, admin):
    with TestClient(app) as ordinary:
        register(ordinary, "person@example.com")
        assert client.post("/admin/password-reset", json=payload(admin_password="incorrect-password")).status_code == 403
        assert client.post("/admin/password-reset", json=payload(password="short")).status_code == 422
        assert client.post("/admin/password-reset", json=payload(), headers={"Origin": "https://other.example"}).status_code == 403
        assert client.post("/admin/password-reset", json=payload(email="missing@example.com")).status_code == 404
        assert client.post("/admin/password-reset", json=payload(email="admin@example.com")).status_code == 403
        assert ordinary.get("/auth/me").status_code == 200
        with SessionLocal() as db:
            assert not db.scalars(select(PasswordResetEvent)).all()


def test_password_reset_is_rate_limited(client, admin):
    for _ in range(5):
        assert client.post("/admin/password-reset", json=payload(admin_password="incorrect-password")).status_code == 403
    response = client.post("/admin/password-reset", json=payload())
    assert response.status_code == 429 and response.headers["Retry-After"] == "300"


def test_admin_role_does_not_grant_access_to_household_finances(client, admin):
    with TestClient(app) as ordinary:
        register(ordinary, "person@example.com")
        response = ordinary.post("/households", json={"name": "Prywatny dom"}, headers={"Idempotency-Key": "admin-privacy-test"})
        assert response.status_code == 201
        household = response.json()["id"]
        assert client.get(f"/households/{household}/overview?month=2026-10").status_code == 403


def test_demo_cannot_log_in_to_an_admin_account(client):
    from app.config import settings

    identifier = register(client, "roch@demo.local")
    with SessionLocal() as db:
        db.get(User, identifier).is_admin = True
        db.commit()
    previous = settings.app_env
    try:
        settings.app_env = "development"
        client.cookies.clear()
        assert client.post("/auth/demo").status_code == 404
        assert client.get("/auth/me").status_code == 401
    finally:
        settings.app_env = previous


def test_provision_admin_creates_account_and_revokes_existing_sessions(client, monkeypatch):
    from app.create_admin import main

    identifier = register(client, "owner@example.com")
    monkeypatch.setattr(sys, "argv", ["create_admin", "OWNER@example.com"])
    main()
    assert client.get("/auth/me").status_code == 401
    assert client.post("/auth/login", json={"email": "owner@example.com", "password": OLD_PASSWORD}).status_code == 200
    assert client.get("/auth/me").json()["user"]["is_admin"] is True
    main()  # Repeat provisioning does not change the password or invalidate a new session.
    assert client.get("/auth/me").status_code == 200
    with SessionLocal() as db:
        assert db.get(User, identifier).is_admin
    monkeypatch.setattr(sys, "argv", ["create_admin", "new-admin@example.com", "--name", "Opiekun"])
    monkeypatch.setattr("getpass.getpass", lambda _: ADMIN_PASSWORD)
    main()
    assert client.post("/auth/login", json={"email": "new-admin@example.com", "password": ADMIN_PASSWORD}).status_code == 200
    assert client.get("/auth/me").json()["user"]["name"] == "Opiekun"
    assert client.get("/auth/me").json()["user"]["is_admin"] is True


def test_provision_admin_rejects_demo_and_bad_passwords(client, monkeypatch):
    from app.create_admin import main

    monkeypatch.setattr(sys, "argv", ["create_admin", "roch@demo.local"])
    with pytest.raises(SystemExit):
        main()
    monkeypatch.setattr(sys, "argv", ["create_admin", "admin@example.com"])
    monkeypatch.setattr("getpass.getpass", lambda _: "short")
    with pytest.raises(SystemExit):
        main()
    with SessionLocal() as db:
        assert not db.scalars(select(User).where(User.is_admin)).all()
