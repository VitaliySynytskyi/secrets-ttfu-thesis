#!/usr/bin/env bash
# Одноразове налаштування VM (Ubuntu 22.04/24.04, OCI Always Free) під TTC-колектор.
# Запускати НА VM з-під ubuntu, після push-code.sh:
#   DOMAIN=<DOMAIN> DUCKDNS_TOKEN=<DUCKDNS_TOKEN> bash /opt/ttc/app/deploy/server/setup.sh
# DUCKDNS_TOKEN необов'язковий (якщо домен не DuckDNS — напр. <ip>.sslip.io).
# Скрипт ідемпотентний: повторний запуск нічого не ламає і НЕ змінює вже згенерований секрет.
set -euo pipefail
: "${DOMAIN:?задай DOMAIN=<DOMAIN>, напр. my-collector.duckdns.org}"
TTC=/opt/ttc
APP=$TTC/app
HERE=$(cd "$(dirname "$0")" && pwd)

# Micro-VM має 1 ГБ RAM: swap-файл страхує apt/pip від OOM.
if ! swapon --show | grep -q /swapfile; then
  sudo fallocate -l 1G /swapfile && sudo chmod 600 /swapfile
  sudo mkswap /swapfile >/dev/null && sudo swapon /swapfile
  grep -q /swapfile /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

# На першому завантаженні apt тримає unattended-upgrades — чекаємо на lock, а не падаємо.
apt_get() { sudo DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=900 "$@"; }
apt_get update
apt_get install -y python3-venv sqlite3 curl gpg debian-keyring debian-archive-keyring \
    apt-transport-https netfilter-persistent iptables-persistent

# --- Caddy (офіційний apt-репозиторій) — reverse proxy з автоматичним HTTPS ---
if ! command -v caddy >/dev/null; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    | sudo tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
  sudo chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg /etc/apt/sources.list.d/caddy-stable.list
  apt_get update
  apt_get install -y caddy
fi

# --- Брандмауер ОС: образи Ubuntu на OCI за замовчуванням REJECT-ять усе, крім 22 ---
for port in 80 443; do
  if ! sudo iptables -C INPUT -m state --state NEW -p tcp --dport "$port" -j ACCEPT 2>/dev/null; then
    n=$(sudo iptables -L INPUT --line-numbers | awk '/REJECT/{print $1; exit}')
    if [ -n "$n" ]; then
      sudo iptables -I INPUT "$n" -m state --state NEW -p tcp --dport "$port" -j ACCEPT
    else
      sudo iptables -A INPUT -m state --state NEW -p tcp --dport "$port" -j ACCEPT
    fi
  fi
done
sudo netfilter-persistent save

# --- Python-оточення (лише залежності колектора, без lifelines/matplotlib — їм на 1 ГБ RAM не місце) ---
[ -d "$TTC/venv" ] || python3 -m venv "$TTC/venv"
"$TTC/venv/bin/pip" install --quiet --upgrade pip
"$TTC/venv/bin/pip" install --quiet "fastapi==0.115.*" "uvicorn==0.34.*"
mkdir -p "$APP/data" "$TTC/backups"

# --- Секрет webhook-шляху: генерується один раз і більше не змінюється ---
sudo mkdir -p /etc/ttc
if [ ! -f /etc/ttc/collector.env ]; then
  secret=$(openssl rand -hex 16)
  sudo tee /etc/ttc/collector.env >/dev/null <<EOF
TTC_DB=$APP/data/ttc.db
TTC_RAW_LOG=$APP/data/raw-events.jsonl
TTC_WEBHOOK_SECRET=$secret
EOF
  sudo chmod 640 /etc/ttc/collector.env
  sudo chown root:ubuntu /etc/ttc/collector.env
fi

# --- systemd-сервіс колектора ---
sudo cp "$HERE/ttc-collector.service" /etc/systemd/system/ttc-collector.service
sudo systemctl daemon-reload
sudo systemctl enable --now ttc-collector
sudo systemctl restart ttc-collector

# --- Caddy: HTTPS → 127.0.0.1:8000 ---
sudo tee /etc/caddy/Caddyfile >/dev/null <<EOF
$DOMAIN {
	reverse_proxy 127.0.0.1:8000
	log {
		output file /var/log/caddy/ttc-access.log
	}
}
EOF
sudo systemctl reload caddy || sudo systemctl restart caddy

# --- cron: щоденний бекап + (опційно) оновлення DuckDNS ---
chmod +x "$HERE/backup.sh"
{
  echo "15 3 * * * ubuntu $HERE/backup.sh >> $TTC/backups/backup.log 2>&1"
  if [ -n "${DUCKDNS_TOKEN:-}" ]; then
    sub=${DOMAIN%%.duckdns.org}
    echo "*/5 * * * * ubuntu curl -fsS 'https://www.duckdns.org/update?domains=$sub&token=$DUCKDNS_TOKEN&ip=' >/dev/null"
  fi
} | sudo tee /etc/cron.d/ttc >/dev/null

# --- Підсумок ---
. <(sudo cat /etc/ttc/collector.env)
sleep 2
echo
echo "Локальна перевірка: $(curl -fsS http://127.0.0.1:8000/healthz || echo 'КОЛЕКТОР НЕ ВІДПОВІДАЄ')"
echo
echo "Webhook URL для КОЖНОГО Canarytoken (тримай у таємниці):"
echo "    https://$DOMAIN/canarytokens/$TTC_WEBHOOK_SECRET"
echo "Healthcheck для UptimeRobot:  https://$DOMAIN/healthz"
