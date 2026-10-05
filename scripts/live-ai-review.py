"""Create isolated live-AI QA servers without printing or copying credentials."""

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/api"))
from app.config import ROOT, settings  # noqa: E402

if not settings.receipt_ai_available:
    raise SystemExit("Selected AI provider is not configured")
qa_db = f"dom_live_{os.getpid()}_test"
qa_images = ROOT / "artifacts" / "live-images" / qa_db
qa_env = dict(
    os.environ,
    DATABASE_URL=settings.database_url.rsplit("/", 1)[0] + "/" + qa_db,
    APP_ENV="development",
    WEB_ORIGIN="http://127.0.0.1:3010",
    RECEIPT_STORAGE=str(qa_images),
)
python = str(ROOT / ".venv/bin/python")
services = []
try:
    subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "db",
            "psql",
            "-U",
            "dom",
            "-d",
            "dom",
            "-c",
            f"CREATE DATABASE {qa_db}",
        ],
        check=True,
    )
    subprocess.run(
        [python, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT / "apps/api",
        env=qa_env,
        check=True,
    )
    for command, cwd, log in [
        (
            [
                python,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8001",
            ],
            ROOT / "apps/api",
            "live-api.log",
        ),
        (
            [
                "node",
                str(ROOT / "node_modules/next/dist/bin/next"),
                "start",
                "--hostname",
                "127.0.0.1",
                "--port",
                "3001",
            ],
            ROOT / "apps/web",
            "live-web.log",
        ),
    ]:
        with (ROOT / "artifacts" / log).open("w") as output:
            services.append(
                subprocess.Popen(
                    command,
                    cwd=cwd,
                    env=qa_env,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                )
            )
    result = subprocess.run(["node", "scripts/live-ai-review.mjs"], cwd=ROOT, env=qa_env, check=False)
    raise SystemExit(result.returncode)
finally:
    for process in services:
        process.terminate()
    for process in services:
        process.wait(timeout=15)
    subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "db",
            "psql",
            "-U",
            "dom",
            "-d",
            "dom",
            "-c",
            f"DROP DATABASE IF EXISTS {qa_db} WITH (FORCE)",
        ],
        check=True,
    )
    import shutil

    shutil.rmtree(qa_images, ignore_errors=True)
