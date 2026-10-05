from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import Member, Period, User


def save(client, household, sources, month="2026-10", **extra):
    return client.put(f"{household['path']}/budget/{month}", json={"income_sources": sources, "allocations": [], **extra})


def test_multiple_sources_exact_totals_months_export_delete(client, household):
    member = household["data"]["members"][0]["id"]
    sources = [
        {"name": "Wynagrodzenie", "member_id": member, "amount": 600001},
        {"name": "Zlecenia", "member_id": member, "amount": 9999},
        {"name": "Najem", "amount": 12345},
    ]
    first = save(client, household, sources)
    assert first.status_code == 200
    assert first.json()["planned_income"] == 622345
    assert first.json()["unassigned"] == 622345
    assert first.json()["income"] == 0  # Planned sources are not booked transactions.
    assert [s["name"] for s in first.json()["income_sources"]] == [s["name"] for s in sources]
    # Repeating PUT replaces rather than appends sources.
    assert save(client, household, sources).status_code == 200
    assert len(client.get(f"{household['path']}/budget/2026-10").json()["income_sources"]) == 3
    assert save(client, household, [{"name": "Premia", "amount": 50000}], "2026-11").json()["planned_income"] == 50000
    assert client.get(f"{household['path']}/budget/2026-10").json()["planned_income"] == 622345
    # Update name, amount, attribution and remove a source.
    assert save(client, household, [{"name": "Zlecenia po korekcie", "amount": 10001}]).json()["planned_income"] == 10001
    exported = client.get(f"{household['path']}/export").json()["income_sources"]
    assert len(exported) == 2
    assert all(s["created_by"] and s["updated_by"] for s in exported)
    assert save(client, household, []).json()["income_sources"] == []
    assert client.request("DELETE", household["path"], json={"name": "Testowy dom"}).status_code == 200


def test_invalid_sources_are_atomic_and_scoped(client, household):
    valid = [{"name": "Pensja", "amount": 100}]
    assert save(client, household, valid).status_code == 200
    with TestClient(app) as stranger:
        stranger.post("/auth/register", json={"name": "Obcy", "email": "other@example.com", "password": "long-secret-password"})
        other = stranger.post("/households", json={"name": "Inny dom"}, headers={"Idempotency-Key": "other-home-key"}).json()
        foreign = stranger.get(f"/households/{other['id']}/overview?month=2026-10").json()["members"][0]["id"]
        assert save(stranger, household, valid).status_code == 403
        assert stranger.get(f"{household['path']}/budget/2026-10").status_code == 403
    assert save(client, household, [{"name": "Pensja", "member_id": foreign, "amount": 900}]).status_code == 404
    invalid = [
        [{"name": "   ", "amount": 10}],
        [{"name": "Pensja", "amount": -1}],
        [{"name": "Pensja", "amount": 1.1}],
        [{"name": "Pensja", "amount": True}],
        [{"name": "Pensja", "amount": "100"}],
        [{"name": "Pensja", "amount": 100_000_000_001}],
        [{"name": "A", "amount": 100_000_000_000}, {"name": "B", "amount": 1}],
        [{"name": " Pensja ", "amount": 10}, {"name": "PENSJA", "amount": 20}],
        [{"name": str(i), "amount": 0} for i in range(51)],
    ]
    for sources in invalid:
        assert save(client, household, sources).status_code == 422
        assert client.get(f"{household['path']}/budget/2026-10").json()["planned_income"] == 100
    assert save(client, household, valid, planned_income=101).status_code == 422
    # Foreign allocations also roll back otherwise-valid income-source changes.
    response = save(
        client, household, [{"name": "Nowa pensja", "amount": 500}], allocations=[{"kind": "pocket", "reference_id": foreign, "amount": 1}]
    )
    assert response.status_code == 404
    assert client.get(f"{household['path']}/budget/2026-10").json()["income_sources"][0]["name"] == "Pensja"


def test_same_source_name_different_people_and_legacy_compatibility(client, household):
    with SessionLocal() as db:
        user = User(name="Kaja", email="kaja@example.com", password_hash="unused")
        db.add(user)
        db.flush()
        member = Member(household_id=household["id"], user_id=user.id, role="member")
        db.add(member)
        db.commit()
        kaja = member.id
    sources = [
        {"name": "Wynagrodzenie", "member_id": household["data"]["members"][0]["id"], "amount": 600000},
        {"name": "Wynagrodzenie", "member_id": kaja, "amount": 400000},
    ]
    assert save(client, household, sources).status_code == 200
    # Allocation-only edits from an older client must retain all source names.
    path = f"{household['path']}/budget/2026-10"
    response = client.put(path, json={"planned_income": 1000000, "allocations": []})
    assert len(response.json()["income_sources"]) == 2
    response = client.put(path, json={"planned_income": 900001, "allocations": []})
    assert response.json()["income_sources"][0]["name"] == "Dochód wspólny"
    assert response.json()["income_sources"][0]["member_id"] is None
    # An old application image can write the legacy total during rollback.
    with SessionLocal() as db:
        period = db.scalar(select(Period).where(Period.household_id == household["id"]))
        period.planned_income = 812345
        db.commit()
    recovered = client.get(path).json()
    assert recovered["planned_income"] == recovered["income_sources"][0]["amount"] == 812345
    assert recovered["income_sources"][0]["member_id"] is None
    response = client.put(path, json={"planned_income": 0, "allocations": []})
    assert response.json()["income_sources"] == []


def test_migration_preserves_existing_plan_and_blocks_destructive_downgrade(client, household, tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path

    from app.db import engine
    from app.models import BudgetAllocation

    api_root = Path(__file__).resolve().parents[1]
    env = {**os.environ, "DATABASE_URL": engine.url.render_as_string(hide_password=False)}

    def migrate(*args):
        return subprocess.run([sys.executable, "-m", "alembic", *args], cwd=api_root, env=env, capture_output=True, text=True)

    assert migrate("downgrade", "004").returncode == 0
    try:
        with SessionLocal() as db:
            period = Period(
                household_id=household["id"], month="2026-09", planned_income=1234567, created_by=household["data"]["members"][0]["user_id"]
            )
            db.add(period)
            db.flush()
            allocation = BudgetAllocation(
                household_id=household["id"],
                period_id=period.id,
                kind="category",
                reference_id=household["data"]["categories"][0]["id"],
                label="Mieszkanie",
                group="Potrzeby",
                amount=50000,
            )
            db.add(allocation)
            db.commit()
            original_id = period.id
        assert migrate("upgrade", "head").returncode == 0
        budget = client.get(f"{household['path']}/budget/2026-09").json()
        assert budget["period"]["id"] == original_id
        assert budget["planned_income"] == budget["income_sources"][0]["amount"] == 1234567
        assert budget["income_sources"][0]["name"] == "Dochód wspólny"
        assert budget["income_sources"][0]["member_id"] is None
        assert budget["assigned"] == 50000
        # Reproduce an old image's Alembic bootstrap against the expanded DB.
        import shutil

        legacy = tmp_path / "legacy-migrations"
        shutil.copytree(api_root / "migrations", legacy)
        (legacy / "versions/005_income_sources.py").unlink()
        bootstrap = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; from alembic.config import Config; from alembic import command; "
                "c=Config('alembic.ini'); c.set_main_option('script_location',sys.argv[1]); command.upgrade(c,'head')",
                str(legacy),
            ],
            cwd=api_root,
            env=env,
            capture_output=True,
            text=True,
        )
        assert bootstrap.returncode != 0
        assert "005" in bootstrap.stderr + bootstrap.stdout
        assert migrate("downgrade", "004").returncode != 0
        assert client.get(f"{household['path']}/budget/2026-09").json()["income_sources"][0]["amount"] == 1234567
    finally:
        assert migrate("upgrade", "head").returncode == 0
