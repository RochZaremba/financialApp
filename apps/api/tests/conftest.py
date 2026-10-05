# ruff: noqa: E402
import os
import uuid
from pathlib import Path

os.environ["DATABASE_URL"] = os.getenv("TEST_DATABASE_URL", "postgresql+psycopg://dom:change-this-local-password@localhost:5434/dom_test")
os.environ["APP_ENV"] = "test"
os.environ["RECEIPT_PROVIDER"] = "fixture"
os.environ["RECEIPT_STORAGE"] = str(Path(__file__).resolve().parents[3] / "artifacts/test-receipts")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from app.db import engine
from app.main import app
from app.security import _attempts


@pytest.fixture(autouse=True)
def clean_database():
    if not engine.url.database.endswith("_test"):
        raise RuntimeError("Tests refuse to run against a non-test database")
    with engine.begin() as conn:
        tables = conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename != 'alembic_version'"))
        names = [row[0] for row in tables]
        if names:
            conn.execute(text("TRUNCATE " + ",".join('"' + name + '"' for name in names) + " CASCADE"))
    _attempts.clear()
    yield


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


@pytest.fixture
def household(client):
    response = client.post("/auth/register", json={"name": "Roch", "email": "roch@example.com", "password": "a-long-test-password"})
    assert response.status_code == 201
    home = client.post("/households", json={"name": "Testowy dom"}, headers={"Idempotency-Key": str(uuid.uuid4())}).json()
    overview = client.get(f"/households/{home['id']}/overview?month=2026-10").json()
    return {"id": home["id"], "path": f"/households/{home['id']}", "data": overview}
