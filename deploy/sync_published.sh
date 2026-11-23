#!/usr/bin/env bash
# З НОУТБУКА: перенести published_at з маніфесту публікації на VM (пакетно, без секретів).
# Маніфест ~/.config/ttc/campaign-published.csv містить token_id,...,published_at —
# саме ці часи треба записати в базу кампанії, інакше TTC рахується від запуску seed.
#   bash deploy/sync_published.sh ubuntu@<public-ip> [~/.ssh/oci.key]
set -euo pipefail
HOST=${1:?ubuntu@<public-ip>}
KEY=${2:-$HOME/.ssh/oci.key}
MAN=${TTC_HOME:-$HOME/.config/ttc}/campaign-published.csv
[ -s "$MAN" ] || { echo "нема $MAN — спершу publish_campaign.py" >&2; exit 1; }
scp -i "$KEY" "$MAN" "$HOST:/tmp/campaign-published.csv"
ssh -i "$KEY" "$HOST" \
  '/opt/ttc/venv/bin/python /opt/ttc/app/deploy/set_published.py \
     --db /opt/ttc/app/data/ttc.db --from-csv /tmp/campaign-published.csv && \
   rm -f /tmp/campaign-published.csv'
echo "published_at синхронізовано ($(( $(wc -l < "$MAN") - 1 )) токенів)"
