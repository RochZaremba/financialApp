#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
test -f .env.production || { printf 'Brak prywatnego .env.production\n' >&2; exit 1; }
chmod 600 .env.production
# Validate before starting; never print the expanded configuration (it contains secrets).
docker compose --env-file .env.production -p finance -f compose.oracle.yaml config --quiet
sudo -n test -f /etc/caddy/Caddyfile
sudo -n caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
docker compose --env-file .env.production -p finance -f compose.oracle.yaml up -d --no-build --wait --wait-timeout 180
curl --fail --silent http://127.0.0.1:8810/api/health > /dev/null
backup_dir="/etc/caddy/finance-backup-$(date -u +%Y%m%dT%H%M%SZ)"
sudo -n mkdir -p "$backup_dir"
sudo -n cp -a /etc/caddy/Caddyfile "$backup_dir/Caddyfile"
had_site=0
if sudo -n test -f /etc/caddy/sites/finance.caddy; then
  sudo -n cp -a /etc/caddy/sites/finance.caddy "$backup_dir/finance.caddy"
  had_site=1
fi
restore_caddy() {
  sudo -n cp -a "$backup_dir/Caddyfile" /etc/caddy/Caddyfile
  if [[ "$had_site" == 1 ]]; then
    sudo -n cp -a "$backup_dir/finance.caddy" /etc/caddy/sites/finance.caddy
  else
    sudo -n rm -f /etc/caddy/sites/finance.caddy
  fi
}
sudo -n install -d -m 755 /etc/caddy/sites
sudo -n install -m 644 deploy/finance.caddy /etc/caddy/sites/finance.caddy
if ! sudo -n grep -q '^import /etc/caddy/sites/finance\.caddy$' /etc/caddy/Caddyfile; then
  printf '\nimport /etc/caddy/sites/finance.caddy\n' | sudo -n tee -a /etc/caddy/Caddyfile > /dev/null
fi
if ! sudo -n caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile; then
  restore_caddy
  printf 'Konfiguracja odrzucona; przywrócono Caddy. Aplikacja pozostaje na loopback.\n' >&2
  exit 1
fi
if ! sudo -n systemctl reload caddy; then
  restore_caddy
  sudo -n systemctl reload caddy
  exit 1
fi
printf 'Uruchomiono https://finance.rochzaremba.com; kopia Caddy: %s\n' "$backup_dir"
