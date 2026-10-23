"""Run administrator recovery checks against an isolated disposable database."""

import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/api"))
from app.config import ROOT, settings  # noqa: E402


def main():
    for port in (3000, 8000):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                raise SystemExit(f"Stop local servers first: port {port} is in use.")
        except OSError:
            pass
    database = f"dom_admin_{os.getpid()}_test"
    storage = ROOT / "artifacts" / "admin-receipts" / database
    artifacts = ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    python = str(ROOT / ".venv/bin/python")
    environment = dict(
        os.environ,
        DATABASE_URL=settings.database_url.rsplit("/", 1)[0] + "/" + database,
        APP_ENV="development",
        RECEIPT_PROVIDER="fixture",
        BUDGET_AI_PROVIDER="history",
        RECEIPT_STORAGE=str(storage),
        DEMO_PASSWORD=secrets.token_urlsafe(24),
        ADMIN_REVIEW_EMAIL="administrator@example.com",
        ADMIN_REVIEW_PASSWORD=secrets.token_urlsafe(24),
        ADMIN_REVIEW_USER_PASSWORD=secrets.token_urlsafe(24),
        WEB_ORIGIN="http://localhost:3000",
        API_INTERNAL_URL="http://127.0.0.1:8000",
    )

    def sql(statement):
        subprocess.run(["docker", "compose", "exec", "-T", "db", "psql", "-U", "dom", "-d", "dom", "-c", statement], cwd=ROOT, check=True)

    services = []
    created = False
    try:
        sql(f"CREATE DATABASE {database}")
        created = True
        for arguments in [["-m", "alembic", "upgrade", "head"], ["-m", "app.seed"]]:
            subprocess.run([python, *arguments], cwd=ROOT / "apps/api", env=environment, check=True)
        # Test-only provisioning, never applied to development or production data.
        provision = (
            "import os; from app.db import SessionLocal; from app.models import User; from app.security import hasher; "
            "db=SessionLocal(); db.add(User(email=os.environ['ADMIN_REVIEW_EMAIL'], name='Administrator', "
            "password_hash=hasher.hash(os.environ['ADMIN_REVIEW_PASSWORD']), is_admin=True)); db.commit(); db.close()"
        )
        subprocess.run([python, "-c", provision], cwd=ROOT / "apps/api", env=environment, check=True)
        with (artifacts / "admin-review-server.log").open("w") as output:
            services.append(
                subprocess.Popen([python, "scripts/serve.py"], cwd=ROOT, env=environment, stdout=output, stderr=subprocess.STDOUT)
            )
        with httpx.Client(trust_env=False, timeout=2) as client:
            for _ in range(45):
                if services[0].poll() is not None:
                    raise RuntimeError("QA server exited; inspect artifacts/admin-review-server.log")
                try:
                    response = client.get("http://localhost:3000/api/health")
                    if response.status_code == 200 and response.json() == {"status": "ok"}:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(1)
            else:
                raise RuntimeError("QA server did not become ready")
        for number in (1, 2):
            review = "scripts/ocr-review.mjs" if "--ocr" in sys.argv else "scripts/admin-review.mjs"
            if "--activity" in sys.argv:
                review = "scripts/activity-review.mjs"
            subprocess.run(["node", review, str(number)], cwd=ROOT, env=environment, check=True)
        if "--regression" in sys.argv:
            arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
            subprocess.run(["npx", "playwright", "test", *arguments], cwd=ROOT / "apps/web", env=environment, check=True)
    finally:
        for service in services:
            service.terminate()
        for service in services:
            try:
                service.wait(timeout=15)
            except subprocess.TimeoutExpired:
                service.kill()
                service.wait()
        if created:
            sql(f"DROP DATABASE {database} WITH (FORCE)")
        shutil.rmtree(storage, ignore_errors=True)


if __name__ == "__main__":
    main()
