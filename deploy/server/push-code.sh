#!/usr/bin/env bash
# З НОУТБУКА (Git Bash): залити код колектора на VM. data/ і .venv НЕ передаються —
# база кампанії живе лише на сервері.
#   bash deploy/server/push-code.sh ubuntu@<public-ip> [~/.ssh/oci.key]
set -euo pipefail
HOST=${1:?ubuntu@<public-ip>}
KEY=${2:-$HOME/.ssh/oci.key}
cd "$(dirname "$0")/../.."
ssh -i "$KEY" "$HOST" 'sudo mkdir -p /opt/ttc/app && sudo chown -R ubuntu:ubuntu /opt/ttc'
tar czf - --exclude=__pycache__ collector deploy | ssh -i "$KEY" "$HOST" 'tar xzf - -C /opt/ttc/app'
echo "код залито; на сервері: sudo systemctl restart ttc-collector (якщо сервіс уже є)"
