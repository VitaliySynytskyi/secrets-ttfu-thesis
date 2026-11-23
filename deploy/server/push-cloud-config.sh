#!/usr/bin/env bash
# З НОУТБУКА: залити на VM ключі читачів журналів і таблиці token_id <-> ключ/роль.
# Опубліковані honeypot-ключі (keys/*.json) НЕ передаються — серверу вони не потрібні.
#   bash deploy/server/push-cloud-config.sh ubuntu@<public-ip> [~/.ssh/oci.key]
set -euo pipefail
HOST=${1:?ubuntu@<public-ip>}
KEY=${2:-$HOME/.ssh/oci.key}
T=${TTC_HOME:-$HOME/.config/ttc}
stage=$(mktemp -d); trap 'rm -rf "$stage"' EXIT
cp "$T/aws/reader.env"     "$stage/aws-reader.env"
cp "$T/aws/users.csv"      "$stage/aws-users.csv"
cp "$T/gcp/accounts.csv"   "$stage/gcp-accounts.csv"
cp "$T/gcp/project"        "$stage/gcp-project"
cp "$T/gcp/reader.json"    "$stage/gcp-reader.json"
cp "$T/db/creds.csv"       "$stage/db-creds.csv"
cp "$T/api/keys.csv"       "$stage/api-keys.csv"
tar czf - -C "$stage" . | ssh -i "$KEY" "$HOST" \
  'sudo mkdir -p /etc/ttc/cloud && sudo tar xzf - -C /etc/ttc/cloud --no-same-owner &&
   sudo chown -R root:ubuntu /etc/ttc/cloud && sudo chmod 750 /etc/ttc/cloud &&
   sudo chmod 640 /etc/ttc/cloud/* && ls /etc/ttc/cloud'
