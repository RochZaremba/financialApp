import json
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_issuer_keeps_bearer_token_outside_repository_and_output(tmp_path):
    destination = tmp_path / "private-token"
    command = [sys.executable, str(ROOT / "scripts/issue-recovery.py"), "fixture@example.com", "--token-file", str(destination)]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=True)
    grant = json.loads(result.stdout)
    token = destination.read_text().strip()
    assert token.startswith(grant["id"] + ".")
    assert token not in result.stdout + result.stderr
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    duplicate = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    assert duplicate.returncode != 0 and destination.read_text().strip() == token
    assert token not in duplicate.stdout + duplicate.stderr
    forbidden = subprocess.run(command[:-1] + [str(ROOT / "unsafe-recovery-token")], cwd=ROOT, capture_output=True, text=True)
    assert forbidden.returncode != 0
    assert not (ROOT / "unsafe-recovery-token").exists()
