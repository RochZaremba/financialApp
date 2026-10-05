#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
version="${1:?release version required}"
commit="${2:?commit SHA required}"
[[ "$version" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ && "$commit" =~ ^[0-9a-f]{40}$ ]]
for role in api web; do
  [[ "$(docker image inspect "finance-$role:$version" --format '{{.Architecture}}')" == arm64 ]]
  [[ "$(docker image inspect "finance-$role:$version" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')" == "$commit" ]]
done
mkdir -p artifacts/release
bundle=$(mktemp -d "$PWD/artifacts/release/bundle.XXXXXX")
trap 'rm -rf "$bundle"' EXIT
docker save "finance-api:$version" "finance-web:$version" | gzip -1 > "$bundle/images.tar.gz"
python3 - "$bundle" "$version" "$commit" <<'PY'
import json
from pathlib import Path
import sys
folder=Path(sys.argv[1])
(folder/'release.json').write_text(json.dumps({'version':sys.argv[2], 'commit':sys.argv[3], 'platform':'linux/arm64', 'repository':'RochZaremba/financialApp'}, indent=2)+'\n')
PY
(cd "$bundle" && sha256sum images.tar.gz release.json > SHA256SUMS)
tar -cf "artifacts/release/finance-$version-arm64.tar" -C "$bundle" images.tar.gz release.json SHA256SUMS
(cd artifacts/release && sha256sum "finance-$version-arm64.tar" > "finance-$version-arm64.tar.sha256")
