"""Own both local servers and stop their process groups before returning."""

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).absolute().parents[1]


def main():
    development = sys.argv[1:] == ["--dev"]
    if sys.argv[1:] not in ([], ["--dev"]):
        raise SystemExit("Użycie: serve.py [--dev]")
    for port in (3000, 8000):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                raise SystemExit(f"Port {port} jest zajęty. Zatrzymaj poprzedni serwer.")
        except OSError:
            pass

    stopped_by = 0

    def stop(signum, frame):
        nonlocal stopped_by
        stopped_by = signum

    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, stop)
    api = [
        str(ROOT / ".venv/bin/python"),
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
        "--timeout-graceful-shutdown",
        "8",
    ]
    if development:
        api.append("--reload")
    commands = [
        (api, ROOT / "apps/api"),
        (
            [
                "node",
                str(ROOT / "node_modules/next/dist/bin/next"),
                "dev" if development else "start",
                "--hostname",
                "127.0.0.1",
            ],
            ROOT / "apps/web",
        ),
    ]
    children = []
    result = 0
    try:
        for command, directory in commands:
            # Ctrl+C reaches only this supervisor. Each complete server tree
            # receives one termination signal, including Uvicorn's reloader.
            children.append(subprocess.Popen(command, cwd=directory, start_new_session=True))
        while not stopped_by:
            exited = next((child for child in children if child.poll() is not None), None)
            if exited:
                result = exited.returncode or 0
                break
            time.sleep(0.1)
    finally:
        for child in children:
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + 10
        for child in children:
            try:
                child.wait(timeout=max(0.1, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                print("Zatrzymujemy pozostałe procesy serwera.", file=sys.stderr)
        # Reap any orphan worker in our own groups, even if its parent exited.
        for child in children:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait()
    return 128 + stopped_by if stopped_by else result


if __name__ == "__main__":
    raise SystemExit(main())
