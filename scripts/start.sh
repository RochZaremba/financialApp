#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
project_root="$PWD"
if [[ ! -f .env || ! -x .venv/bin/python || ! -f apps/web/.next/BUILD_ID ]]; then
  printf "Najpierw wykonaj ./scripts/setup.sh i npm run build\n" >&2
  exit 1
fi
docker compose up -d --wait db
(cd apps/api && "$project_root/.venv/bin/python" -m alembic upgrade head)
set -a
source .env
set +a
exec "$project_root/.venv/bin/python" scripts/serve.py
