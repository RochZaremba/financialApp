#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
project_root="$PWD"
if [[ ! -f .env || ! -x .venv/bin/python ]]; then
  printf 'Najpierw uruchom ./scripts/setup.sh\n' >&2
  exit 1
fi
docker compose up -d --wait db
(cd apps/api && "$project_root/.venv/bin/python" -m alembic upgrade head)
set -a
source .env
set +a
exec "$project_root/.venv/bin/python" scripts/serve.py --dev
