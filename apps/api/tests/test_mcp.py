import base64
import json
import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.db import SessionLocal
from app.main import app
from app.models import Audit, MCPConnection, Member, MeterReading, User
from app.security import digest

PASSWORD = "a-long-test-password"


def connect(client, household, access="write"):
    result = client.post(household["path"] + "/connections", json={"name": "Test AI", "access": access, "password": PASSWORD})
    assert result.status_code == 201, result.text
    data = result.json()
    return data, {"Authorization": "Bearer " + data["token"], "Accept": "application/json, text/event-stream"}


def rpc(client, headers, method, params=None):
    return client.post("/mcp/", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}})


def call(client, headers, name, **arguments):
    response = rpc(client, headers, "tools/call", {"name": name, "arguments": arguments})
    assert response.status_code == 200, response.text
    return response.json()["result"]


def content(result):
    assert not result.get("isError"), result
    return json.loads(result["content"][0]["text"])


def test_sdk_initialize_catalog_and_real_reading_roundtrip(client, household):
    connection, headers = connect(client, household)
    initialized = rpc(
        client, headers, "initialize", {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "QA", "version": "1"}}
    )
    assert initialized.status_code == 200
    assert initialized.json()["result"]["serverInfo"]["name"] == "Razem"
    tools = rpc(client, headers, "tools/list").json()["result"]["tools"]
    names = {t["name"] for t in tools}
    assert {
        "reading_create",
        "transaction_create",
        "budget_save",
        "shopping_purchase",
        "activity",
        "receipt_upload",
        "household_delete",
    } <= names
    assert not any("connection" in name or "password" in name or "invitation" in name for name in names)
    assert content(call(client, headers, "app_context"))["household_id"] == household["id"]
    meter = content(call(client, headers, "meter_create", data={"name": "Prąd", "unit": "kWh"}, idempotency_key=str(uuid.uuid4())))
    key = str(uuid.uuid4())
    args = {
        "meter_id": meter["id"],
        "data": {"date": "2026-01-01", "value": 123456, "time": "08:15", "activities": {"oven": False}, "note": "Bez pieczenia"},
        "idempotency_key": key,
    }
    first = content(call(client, headers, "reading_create", **args))
    assert content(call(client, headers, "reading_create", **args))["id"] == first["id"]
    detail = content(call(client, headers, "meter_read", meter_id=meter["id"]))
    assert detail["readings"][0]["value"] == 123456
    assert detail["readings"][0]["time"] == "08:15" and detail["readings"][0]["activities"] == {"oven": False}
    assert detail["readings"][0]["note"] == "Bez pieczenia"
    assert detail["readings"][0]["created_by_name"] == "Roch"
    with SessionLocal() as db:
        assert db.scalar(select(MeterReading)).created_by == detail["readings"][0]["created_by"]
        grant = db.get(MCPConnection, connection["connection"]["id"])
        assert grant.token_hash == digest(connection["token"]) and grant.last_used_at
        events = list(db.scalars(select(Audit).where(Audit.action == "mcp.call")))
        assert events and all(set(event.details) == {"tool", "status"} for event in events)


def test_scope_readonly_and_no_security_or_cross_household_access(client, household):
    data, headers = connect(client, household, "read")
    assert content(call(client, headers, "meter_list")) == []
    assert call(client, headers, "meter_create", data={"name": "X", "unit": "m3"}, idempotency_key="scope-test-123")["isError"]
    assert client.get(household["path"] + "/connections", headers=headers).status_code == 403
    assert client.get("/auth/me", headers=headers).status_code == 403
    assert client.post(household["path"] + "/invitations", headers=headers).status_code == 403
    assert client.get("/households/not-authorized/meters", headers=headers).status_code == 403
    assert call(client, headers, "meter_read", meter_id="missing", household_id="other")["isError"]
    assert client.delete(household["path"] + "/connections/" + data["connection"]["id"]).status_code == 200
    assert rpc(client, headers, "tools/list").status_code == 401


def test_expiry_membership_and_cookie_is_not_mcp_auth(client, household):
    data, headers = connect(client, household)
    assert rpc(client, {}, "tools/list").status_code == 401
    with SessionLocal() as db:
        row = db.get(MCPConnection, data["connection"]["id"])
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    assert rpc(client, headers, "tools/list").status_code == 401
    data, headers = connect(client, household)
    with SessionLocal() as db:
        db.execute(delete(Member).where(Member.household_id == household["id"]))
        db.commit()
    assert rpc(client, headers, "tools/list").status_code == 401


def test_creation_requires_password_and_connection_is_private(client, household):
    response = client.post(household["path"] + "/connections", json={"name": "AI", "password": "wrong-password"})
    assert response.status_code == 403
    data, _ = connect(client, household)
    listed = client.get(household["path"] + "/connections").json()
    assert data["token"] not in json.dumps(listed) and "token_hash" not in json.dumps(listed)
    invitation = client.post(household["path"] + "/invitations").json()["token"]
    with TestClient(app) as second:
        second.post("/auth/register", json={"email": "second@example.com", "name": "Kaja", "password": PASSWORD})
        assert second.post("/households/join", json={"token": invitation}).status_code == 200
        assert second.get(household["path"] + "/connections").json() == []
        assert second.delete(household["path"] + "/connections/" + data["connection"]["id"]).status_code == 404


def test_photo_proposal_and_manual_value_validation(client, household):
    from pathlib import Path

    _, headers = connect(client, household)
    meter = content(call(client, headers, "meter_create", data={"name": "Prąd", "unit": "kWh"}, idempotency_key="photo-meter-123"))
    fixture = Path(__file__).resolve().parents[3] / "fixtures/meter.png"
    result = content(
        call(
            client,
            headers,
            "meter_photo",
            meter_id=meter["id"],
            image_base64=base64.b64encode(fixture.read_bytes()).decode(),
            idempotency_key="photo-upload-123",
        )
    )
    assert result["proposal"]["value"] == 12345678
    assert content(call(client, headers, "meter_read", meter_id=meter["id"]))["readings"] == []
    invalid = call(
        client,
        headers,
        "reading_create",
        meter_id=meter["id"],
        data={"date": "2026-01-01", "value": 12.34},
        idempotency_key="bad-meter-value",
    )
    assert invalid["isError"]
    invalid = call(
        client,
        headers,
        "meter_photo",
        meter_id=meter["id"],
        image_base64="https://private.example/image",
        idempotency_key="bad-photo-value",
    )
    assert invalid["isError"]


def test_delete_confirmation_and_origin_rejection(client, household):
    _, headers = connect(client, household)
    assert call(client, headers, "household_delete", data={"name": "Testowy dom"})["isError"]
    assert call(client, headers, "household_delete", data={"name": "Testowy dom"}, confirm_delete=False)["isError"]
    assert rpc(client, {**headers, "Origin": "https://evil.example"}, "tools/list").status_code == 403
    result = content(call(client, headers, "household_delete", data={"name": "Testowy dom"}, confirm_delete=True))
    assert result == {"ok": True}
    assert rpc(client, headers, "tools/list").status_code == 401


def test_money_idempotency_invalid_allocations_and_stale_reading_edit(client, household):
    _, headers = connect(client, household)
    data = {
        "kind": "expense",
        "amount": 1234,
        "date": "2026-01-01",
        "description": "MCP test",
        "account_id": household["data"]["accounts"][0]["id"],
        "allocations": [{"category_id": household["data"]["categories"][0]["id"], "amount": 1234}],
    }
    args = {"data": data, "idempotency_key": "money-through-mcp"}
    created = content(call(client, headers, "transaction_create", **args))
    assert content(call(client, headers, "transaction_create", **args))["id"] == created["id"]
    invalid = {**data, "amount": 1235}
    assert call(client, headers, "transaction_create", data=invalid, idempotency_key="invalid-money-mcp")["isError"]
    meter = content(call(client, headers, "meter_create", data={"name": "Woda", "unit": "m3"}, idempotency_key="water-meter-mcp"))
    row = content(
        call(
            client,
            headers,
            "reading_create",
            meter_id=meter["id"],
            data={"date": "2026-01-01", "value": 12000},
            idempotency_key="water-reading-mcp",
        )
    )
    edited = content(
        call(
            client,
            headers,
            "reading_edit",
            meter_id=meter["id"],
            reading_id=row["id"],
            data={"date": row["date"], "value": 13000, "expected_updated_at": row["updated_at"]},
        )
    )
    assert edited["value"] == 13000
    assert call(
        client,
        headers,
        "reading_edit",
        meter_id=meter["id"],
        reading_id=row["id"],
        data={"date": row["date"], "value": 14000, "expected_updated_at": row["updated_at"]},
    )["isError"]


def test_admin_reset_revokes_keys_and_mcp_cannot_reach_admin(client, household):
    _, headers = connect(client, household)
    assert (
        client.post(
            "/admin/password-reset", headers=headers, json={"email": "roch@example.com", "password": PASSWORD, "admin_password": PASSWORD}
        ).status_code
        == 403
    )
    with TestClient(app) as admin:
        response = admin.post("/auth/register", json={"email": "admin-mcp@example.com", "password": PASSWORD})
        with SessionLocal() as db:
            db.get(User, response.json()["id"]).is_admin = True
            db.commit()
        reset = admin.post(
            "/admin/password-reset", json={"email": "roch@example.com", "password": "new-test-password", "admin_password": PASSWORD}
        )
        assert reset.status_code == 200
    assert rpc(client, headers, "tools/list").status_code == 401


def test_mcp_body_limit_unknown_tools_and_no_slash_redirect(client, household):
    _, headers = connect(client, household)
    response = client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, follow_redirects=False)
    assert response.status_code == 200 and "location" not in response.headers
    assert rpc(client, {**headers, "Host": "api:8000"}, "tools/list").status_code == 200
    assert rpc(client, {**headers, "Host": "untrusted.example"}, "tools/list").status_code == 421
    assert call(client, headers, "run_sql", query="SELECT password_hash FROM users")["isError"]
    response = client.post("/mcp", headers={**headers, "Content-Length": str(15 * 1024 * 1024)}, content=b"{}")
    assert response.status_code == 413


def test_host_password_recovery_revokes_ai_connections(client, household, monkeypatch):
    import sys
    from app import reset_password

    _, headers = connect(client, household)
    monkeypatch.setattr(sys, "argv", ["reset_password", "roch@example.com"])
    monkeypatch.setattr(reset_password.getpass, "getpass", lambda _: "new-host-test-password")
    reset_password.main()
    assert rpc(client, headers, "tools/list").status_code == 401
