#!/usr/bin/env bash
# З НОУТБУКА: щоденний знімок кампанії + звіт (хто/коли/звідки використав токени).
#   bash deploy/monitor.sh ubuntu@<public-ip> [~/.ssh/oci.key]
set -euo pipefail
HOST=${1:?ubuntu@<public-ip>}
KEY=${2:-$HOME/.ssh/oci.key}
cd "$(dirname "$0")/.."
PY=.venv/Scripts/python.exe
# Консоль Windows за замовчуванням cp1252 — без цього print() кирилиці падає з UnicodeEncodeError.
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8
MAN=${TTC_HOME:-$HOME/.config/ttc}/campaign-published.csv

bash deploy/server/pull-data.sh "$HOST" "$KEY" >/dev/null
latest=$(ls -dt data/campaign/*/ | head -1)
echo "== Знімок: $latest =="
"$PY" deploy/campaign_status.py --db "$latest/ttc.db" \
  ${MAN:+--published "$MAN"} --seed-run-at "$(date -u +%Y-%m-%dT%H)"
