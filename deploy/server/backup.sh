#!/usr/bin/env bash
# Щоденний консистентний знімок бази й сирого журналу на VM (cron з setup.sh).
# Це захист від пошкодження файлу; від втрати самої VM захищає pull-data.sh (копія на ноутбук).
set -euo pipefail
DATA=/opt/ttc/app/data
OUT=/opt/ttc/backups
stamp=$(date -u +%Y%m%dT%H%MZ)
sqlite3 "$DATA/ttc.db" ".backup '$OUT/ttc-$stamp.db'"
[ -f "$DATA/raw-events.jsonl" ] && cp "$DATA/raw-events.jsonl" "$OUT/raw-events-$stamp.jsonl"
find "$OUT" -name 'ttc-*.db' -mtime +30 -delete
find "$OUT" -name 'raw-events-*.jsonl' -mtime +30 -delete
echo "$stamp ok"
