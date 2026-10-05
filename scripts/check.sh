#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
project_root="$PWD"
mkdir -p artifacts
if [[ "${1:-}" != "" && "${1:-}" != "--static" ]]; then
  printf 'Użycie: ./scripts/check.sh [--static]\n' >&2
  exit 1
fi
# Building into .next while Next is serving it can invalidate live chunks.
# The complete check starts its own servers from the build under test.
check_mode="${1:-full}"
python3 - "$check_mode" <<'PY'
import socket
import sys
ports = [3000] if sys.argv[1] == '--static' else [3000, 8000]
for port in ports:
    try:
        connection = socket.create_connection(('127.0.0.1', port), timeout=0.3)
    except OSError:
        continue
    connection.close()
    sys.exit(f'Port {port} jest zajęty. Zatrzymaj lokalny serwer przed check.sh (Ctrl+C).')
PY
npm run lint
npm run typecheck
npm test
npm run build
(cd apps/api && "$project_root/.venv/bin/python" -m ruff check app tests migrations && "$project_root/.venv/bin/python" -m ruff format --check app tests migrations)
"$project_root/.venv/bin/python" -m ruff check --config apps/api/pyproject.toml scripts
"$project_root/.venv/bin/python" -m ruff format --check --config apps/api/pyproject.toml scripts
"$project_root/.venv/bin/python" -m ruff check --config apps/api/pyproject.toml deploy/ci-deploy.py
"$project_root/.venv/bin/python" -m ruff format --check --config apps/api/pyproject.toml deploy/ci-deploy.py
"$project_root/.venv/bin/python" -m pytest -q scripts/tests
docker compose up -d --wait db
# A separate database. Never truncate development/production data.
docker compose exec -T db psql -U dom -d dom -tc "SELECT 1 FROM pg_database WHERE datname='dom_test'" | rg -q 1 || docker compose exec -T db psql -U dom -d dom -c 'CREATE DATABASE dom_test'
set -a
source .env
set +a
(cd apps/api && TEST_DATABASE_URL="${DATABASE_URL%/*}/dom_test" DATABASE_URL="${DATABASE_URL%/*}/dom_test" "$project_root/.venv/bin/python" -m alembic upgrade head && TEST_DATABASE_URL="${DATABASE_URL%/*}/dom_test" "$project_root/.venv/bin/python" -m pytest -q)
if [[ "$check_mode" == "full" ]]; then
  api_pid=''
  web_pid=''
  qa_database="dom_browser_$$_test"
  qa_receipts="$project_root/artifacts/browser-receipts/$qa_database"
  cleanup(){
    [[ -z "$api_pid" ]] || kill "$api_pid" 2>/dev/null || true
    [[ -z "$web_pid" ]] || kill "$web_pid" 2>/dev/null || true
    [[ -z "$api_pid" ]] || wait "$api_pid" 2>/dev/null || true
    [[ -z "$web_pid" ]] || wait "$web_pid" 2>/dev/null || true
    docker compose exec -T db psql -U dom -d dom -c "DROP DATABASE IF EXISTS $qa_database WITH (FORCE)" > /dev/null
    "$project_root/.venv/bin/python" -c 'import shutil,sys; shutil.rmtree(sys.argv[1], ignore_errors=True)' "$qa_receipts"
  }
  trap cleanup EXIT INT TERM
  docker compose exec -T db psql -U dom -d dom -c "CREATE DATABASE $qa_database"
  # No paid AI calls or writes to development data during browser tests.
  export DATABASE_URL="${DATABASE_URL%/*}/$qa_database"
  export APP_ENV=development RECEIPT_PROVIDER=fixture RECEIPT_STORAGE="$qa_receipts"
  export DEMO_PASSWORD="$("$project_root/.venv/bin/python" -c 'import secrets; print(secrets.token_urlsafe(24))')"
  (cd apps/api && "$project_root/.venv/bin/python" -m alembic upgrade head && "$project_root/.venv/bin/python" -m app.seed)
  (cd apps/api && exec "$project_root/.venv/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port 8000) > artifacts/check-server.log 2>&1 &
  api_pid=$!
  (cd apps/web && exec node "$project_root/node_modules/next/dist/bin/next" start --hostname 127.0.0.1) >> artifacts/check-server.log 2>&1 &
  web_pid=$!
  ready=0
  for _ in {1..60}; do
    if curl --fail --silent http://localhost:3000/api/health > /dev/null; then ready=1; break; fi
    if ! kill -0 "$api_pid" 2>/dev/null || ! kill -0 "$web_pid" 2>/dev/null; then break; fi
    sleep 1
  done
  if [[ "$ready" != 1 ]]; then
    printf 'Serwer nie uruchomił się. Sprawdź artifacts/check-server.log.\n' >&2
    exit 1
  fi
  if [[ "${PLAYWRIGHT_DOCKER:-0}" == "1" ]]; then
    browser_version="$(node -p 'require("@playwright/test/package.json").version')"
    docker run --rm --user "$(id -u):$(id -g)" --network host --ipc=host \
      -v "$PWD:/work" -w /work -e WEBKIT="${WEBKIT:-0}" -e REVIEW_PASS="${REVIEW_PASS:-check}" \
      -e HOME=/tmp -e NPM_CONFIG_CACHE=/tmp/npm-cache \
      "mcr.microsoft.com/playwright:v${browser_version}-noble" sh -c '
        npm run e2e &&
        node scripts/visual-review.mjs "$REVIEW_PASS" &&
        node scripts/state-review.mjs "$REVIEW_PASS-states" &&
        node scripts/release-probes.mjs "$REVIEW_PASS-probes" --verify
      '
  else
    npm run e2e
    node scripts/visual-review.mjs "${REVIEW_PASS:-check}"
    node scripts/state-review.mjs "${REVIEW_PASS:-check}-states"
    node scripts/release-probes.mjs "${REVIEW_PASS:-check}-probes" --verify
  fi
fi
