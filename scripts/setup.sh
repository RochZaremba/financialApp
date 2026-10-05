#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
project_root="$PWD"
if [[ ! -f .env ]]; then
  python3 - <<'PY'
from pathlib import Path
import secrets
password=secrets.token_urlsafe(24)
config=Path('.env.example').read_text().replace('change-this-local-password',password).replace('RECEIPT_PROVIDER=manual','RECEIPT_PROVIDER=fixture')
Path('.env').write_text(config)
Path('.env').chmod(0o600)
PY
fi
mkdir -p artifacts
python3 -m venv .venv
.venv/bin/python -m pip install -r apps/api/requirements.lock.txt
npm ci
docker compose up -d --wait db
(cd apps/api && "$project_root/.venv/bin/python" -m alembic upgrade head && "$project_root/.venv/bin/python" -m app.seed)
printf '\nGotowe. Uruchom ./scripts/dev.sh i otwórz http://localhost:3000\n'
