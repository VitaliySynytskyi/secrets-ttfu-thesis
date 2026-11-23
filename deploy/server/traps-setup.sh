#!/usr/bin/env bash
# Пастки для основної кампанії (НА VM, після push-code.sh і push-cloud-config.sh):
#   DOMAIN=<DOMAIN> bash /opt/ttc/app/deploy/server/traps-setup.sh
#
#  * Postgres-пастка (Docker, postgres:16-alpine, ліміт 192 МБ) на :5432:
#    ролі з опублікованими логінами/паролями, CONNECT на всі бази відкликано, superuser
#    ззовні заборонений (pg_hba reject). csvlog -> /var/lib/ttc/pglog (читає ttc-poller);
#  * API-пастка: Caddy api.$DOMAIN -> колектор /api-trap/*;
#  * ttc-poller: CloudTrail + GCP Audit Logs + журнал Postgres -> ttc.db.
# Ідемпотентний.
set -euo pipefail
: "${DOMAIN:?задай DOMAIN=<DOMAIN>, напр. my-collector.duckdns.org}"
TTC=/opt/ttc
HERE=$(cd "$(dirname "$0")" && pwd)
CLOUD=/etc/ttc/cloud
for f in aws-reader.env aws-users.csv gcp-accounts.csv gcp-project gcp-reader.json db-creds.csv api-keys.csv; do
  sudo test -s "$CLOUD/$f" || { echo "нема $CLOUD/$f — спершу push-cloud-config.sh" >&2; exit 1; }
done

apt_get() { sudo DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=900 "$@"; }
command -v docker >/dev/null || { apt_get update; apt_get install -y docker.io; }
sudo systemctl enable --now docker

# --- Postgres-пастка ---
sudo mkdir -p /var/lib/ttc/pgdata /var/lib/ttc/pglog /etc/ttc/pg
sudo chown 70:70 /var/lib/ttc/pglog && sudo chmod 755 /var/lib/ttc/pglog   # uid postgres в alpine
sudo tee /etc/ttc/pg/pg_hba.conf >/dev/null <<'EOF'
local all all              trust
host  all postgres 0.0.0.0/0 reject
host  all postgres ::/0      reject
host  all all      0.0.0.0/0 scram-sha-256
host  all all      ::/0      scram-sha-256
EOF
if ! sudo docker ps -a --format '{{.Names}}' | grep -qx pg-trap; then
  sudo docker run -d --name pg-trap --restart always --memory 192m -p 5432:5432 \
    -e POSTGRES_PASSWORD="$(openssl rand -hex 24)" \
    -v /var/lib/ttc/pgdata:/var/lib/postgresql/data \
    -v /var/lib/ttc/pglog:/var/log/pg \
    -v /etc/ttc/pg/pg_hba.conf:/etc/ttc/pg_hba.conf:ro \
    postgres:16-alpine \
    -c hba_file=/etc/ttc/pg_hba.conf -c log_connections=on -c logging_collector=on \
    -c log_destination=csvlog -c log_directory=/var/log/pg \
    -c 'log_filename=postgresql-%Y-%m-%d.log' -c log_file_mode=0644 \
    -c shared_buffers=32MB -c max_connections=40 -c password_encryption=scram-sha-256
fi
for _ in $(seq 1 30); do sudo docker exec pg-trap pg_isready -q -U postgres && break; sleep 2; done

# ролі: рівно опубліковані логіни/паролі; без CONNECT => вхід правильним паролем
# фіксується (`connection authorized`) і одразу обривається `permission denied`
sudo cat "$CLOUD/db-creds.csv" | python3 -c '
import csv, sys
q = lambda s: s.replace("\x27", "\x27\x27")
print("SELECT 1;")
for r in csv.DictReader(sys.stdin):
    u, p = r["user"], q(r["password"])
    print(f"DO $$BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname=\x27{u}\x27) "
          f"THEN CREATE ROLE \"{u}\" LOGIN CONNECTION LIMIT 3 PASSWORD \x27{p}\x27; END IF; END$$;")
' | sudo docker exec -i pg-trap psql -q -U postgres -v ON_ERROR_STOP=1 >/dev/null
sudo docker exec pg-trap psql -q -U postgres -tc "SELECT 1 FROM pg_database WHERE datname='app'" \
  | grep -q 1 || sudo docker exec pg-trap psql -q -U postgres -c "CREATE DATABASE app"
sudo docker exec pg-trap psql -q -U postgres -c \
  "REVOKE CONNECT ON DATABASE app, postgres, template1 FROM PUBLIC"

# брандмауер ОС: 5432 (у Security List OCI порт відкрити окремо!)
if ! sudo iptables -C INPUT -m state --state NEW -p tcp --dport 5432 -j ACCEPT 2>/dev/null; then
  n=$(sudo iptables -L INPUT --line-numbers | awk '/REJECT/{print $1; exit}')
  sudo iptables -I INPUT "${n:-1}" -m state --state NEW -p tcp --dport 5432 -j ACCEPT
  sudo netfilter-persistent save
fi

# --- API-пастка: ключі для колектора + Caddy ---
grep -q '^TTC_API_KEYS=' /etc/ttc/collector.env \
  || echo "TTC_API_KEYS=$CLOUD/api-keys.csv" | sudo tee -a /etc/ttc/collector.env >/dev/null
if ! sudo grep -q "^api.$DOMAIN" /etc/caddy/Caddyfile; then
  sudo tee -a /etc/caddy/Caddyfile >/dev/null <<EOF

api.$DOMAIN {
	rewrite * /api-trap{uri}
	reverse_proxy 127.0.0.1:8000
	log {
		output file /var/log/caddy/ttc-api-access.log
	}
}
EOF
  sudo systemctl reload caddy
fi
sudo systemctl restart ttc-collector

# --- опитувач ---
"$TTC/venv/bin/pip" install --quiet "boto3==1.*" "google-auth==2.*" "requests==2.*"
sudo cp "$HERE/ttc-poller.service" /etc/systemd/system/ttc-poller.service
sudo systemctl daemon-reload
sudo systemctl enable --now ttc-poller
sudo systemctl restart ttc-poller
sleep 3
systemctl --no-pager --lines=5 status ttc-poller | tail -6
echo "pg-trap: $(sudo docker inspect -f '{{.State.Status}}' pg-trap)"
