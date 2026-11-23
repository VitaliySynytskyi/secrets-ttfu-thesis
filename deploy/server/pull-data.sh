#!/usr/bin/env bash
# З НОУТБУКА: забрати з VM консистентну копію бази й сирий журнал у data/campaign/<дата>/.
# Запускати хоча б раз на день-два: це єдиний захист від втрати VM.
#   bash deploy/server/pull-data.sh ubuntu@<public-ip> [~/.ssh/oci.key]
set -euo pipefail
HOST=${1:?ubuntu@<public-ip>}
KEY=${2:-$HOME/.ssh/oci.key}
cd "$(dirname "$0")/../.."
dest=data/campaign/$(date -u +%Y%m%dT%H%MZ)
mkdir -p "$dest"
ssh -i "$KEY" "$HOST" "sqlite3 -cmd '.timeout 30000' /opt/ttc/app/data/ttc.db \".backup '/tmp/ttc-pull.db'\""
scp -i "$KEY" "$HOST:/tmp/ttc-pull.db" "$dest/ttc.db"
scp -i "$KEY" "$HOST:/opt/ttc/app/data/raw-events.jsonl" "$dest/" 2>/dev/null || echo "(сирий журнал поки порожній)"
# Сирий журнал опитувача (CloudTrail/GCP Audit) — первинне джерело викликів, напр. Bedrock (ai_abuse_trend у plan.md).
scp -i "$KEY" "$HOST:/opt/ttc/app/data/raw-cloud-events.jsonl" "$dest/" 2>/dev/null || echo "(журнал опитувача поки порожній)"
.venv/Scripts/python.exe deploy/export.py --db "$dest/ttc.db" --out "$dest/ttc.csv"
echo "-> $dest"
