#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
test -n "${FINANCE_RELEASE:-}"
mkdir -p artifacts
task_root=$(mktemp -d "$PWD/artifacts/production-smoke.XXXXXX")
qa_project="finance_smoke_$$"
cleanup() {
  docker compose -p "$qa_project" -f "$task_root/compose.json" logs --no-color > artifacts/production-smoke.log 2>&1 || true
  docker compose -p "$qa_project" -f "$task_root/compose.json" down -v > /dev/null 2>&1 || true
  rm -rf "$task_root"
}
trap cleanup EXIT
python3 - "$task_root" "$FINANCE_RELEASE" <<'PY'
from pathlib import Path
import secrets,sys
folder=Path(sys.argv[1])
(folder/'.env.qa').write_text('FINANCE_RELEASE='+sys.argv[2]+'\nPOSTGRES_PASSWORD='+secrets.token_urlsafe(32)+'\nDOMAIN=budget.localhost:8443\nRECEIPT_PROVIDER=manual\nGEMINI_API_KEY=\nOPENAI_API_KEY=\n')
(folder/'Caddyfile').write_text('budget.localhost {\n tls internal\n reverse_proxy web:3000\n}\n')
PY
docker compose --env-file "$task_root/.env.qa" -p "$qa_project" -f compose.oracle.yaml config --format json > "$task_root/base.json"
python3 - "$task_root" <<'PY'
import json,sys
from pathlib import Path
folder=Path(sys.argv[1])
config=json.loads((folder/'base.json').read_text())
config['services']['web'].pop('ports',None)
config['services']['api']['environment'].update(WEB_ORIGIN='https://budget.localhost:8443',RECEIPT_PROVIDER='manual',GEMINI_API_KEY='',OPENAI_API_KEY='')
config['services']['proxy']={'image':'caddy:2-alpine','ports':[{'target':443,'published':'8443','host_ip':'127.0.0.1','protocol':'tcp'}],'volumes':[{'type':'bind','source':str(folder/'Caddyfile'),'target':'/etc/caddy/Caddyfile','read_only':True}],'depends_on':{'web':{'condition':'service_healthy'}}}
(folder/'compose.json').write_text(json.dumps(config))
PY
docker compose -p "$qa_project" -f "$task_root/compose.json" up -d --no-build --wait --wait-timeout 180
[[ "$(docker compose -p "$qa_project" -f "$task_root/compose.json" exec -T db psql -U dom -d dom -tAc 'SELECT count(*) FROM users')" == 0 ]]
docker compose -p "$qa_project" -f "$task_root/compose.json" exec -T api python -c 'from pathlib import Path; assert not Path("/app/fixtures").exists(); assert not Path("/app/apps/api/app/seed.py").exists()'
docker compose -p "$qa_project" -f "$task_root/compose.json" exec -T web sh -c 'test ! -e /app/apps/web/public/demo'
# Exercise the actual deployment helper with empty and populated private storage.
python3 - "$task_root" "$FINANCE_RELEASE" <<'PY'
import importlib.util,json,tarfile,sys
from pathlib import Path
folder=Path(sys.argv[1])
config=json.loads((folder/'compose.json').read_text())
volume=config['volumes']['receipt_data']['name']
spec=importlib.util.spec_from_file_location('receiver','deploy/ci-deploy.py')
receiver=importlib.util.module_from_spec(spec)
spec.loader.exec_module(receiver)
receiver.backup_receipts('finance-api:'+sys.argv[2],volume,folder/'empty-receipts.tar.gz')
with tarfile.open(folder/'empty-receipts.tar.gz') as archive:
    assert any(item.isdir() and item.name.rstrip('/')=='receipts' for item in archive)
print('Real empty receipt-volume backup passed.')
PY
docker compose -p "$qa_project" -f "$task_root/compose.json" exec -T api python -c 'from pathlib import Path; Path("/data/receipts/qa-backup-marker").write_text("synthetic backup fixture")'
python3 - "$task_root" "$FINANCE_RELEASE" <<'PY'
import importlib.util,json,tarfile,sys
from pathlib import Path
folder=Path(sys.argv[1])
volume=json.loads((folder/'compose.json').read_text())['volumes']['receipt_data']['name']
spec=importlib.util.spec_from_file_location('receiver','deploy/ci-deploy.py')
receiver=importlib.util.module_from_spec(spec)
spec.loader.exec_module(receiver)
receiver.backup_receipts('finance-api:'+sys.argv[2],volume,folder/'populated-receipts.tar.gz')
with tarfile.open(folder/'populated-receipts.tar.gz') as archive:
    assert archive.extractfile('receipts/qa-backup-marker').read()==b'synthetic backup fixture'
print('Real populated receipt-volume backup passed.')
PY
PRODUCTION_REVIEW_URL=https://budget.localhost:8443 node scripts/production-review.mjs
