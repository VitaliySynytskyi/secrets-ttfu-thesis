#!/usr/bin/env bash
# З НОУТБУКА: перенести часи публікації на VM одним викликом.
# CSV — колонки token_id, published_at (ISO 8601 з часовою зоною); інші колонки ігноруються.
# Перевірка «все або нічого»: якщо хоч один рядок поганий, база не змінюється.
#   bash deploy/server/sync-published.sh ubuntu@<public-ip> <published.csv> [~/.ssh/oci.key]
set -euo pipefail
HOST=${1:?ubuntu@<public-ip>}
CSV=${2:?шлях до CSV з token_id,published_at}
KEY=${3:-$HOME/.ssh/oci.key}
scp -i "$KEY" -q "$CSV" "$HOST:/tmp/ttc-published.csv"
ssh -i "$KEY" "$HOST" 'cd /opt/ttc/app &&
  /opt/ttc/venv/bin/python deploy/set_published.py --db data/ttc.db --from-csv /tmp/ttc-published.csv;
  rc=$?; rm -f /tmp/ttc-published.csv; exit $rc'
