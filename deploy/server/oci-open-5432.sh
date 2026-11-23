#!/usr/bin/env bash
# Відкрити TCP 5432 (Postgres-пастка) у Security List підмережі VM через OCI CLI.
# Додає правило до наявних (update замінює весь список, тому спершу читаємо поточний).
#   VM_HOST=<VM_HOST> bash deploy/server/oci-open-5432.sh
# oci-ids.env (поза репозиторієм) має задавати SUB=<OCI_SUBNET_OCID>.
set -euo pipefail
export OCI_CLI_SUPPRESS_FILE_PERMISSIONS_WARNING=True
cd "$(dirname "$0")/../.."
set -a; . "${TTC_HOME:-$HOME/.config/ttc}/oci-ids.env"; set +a
PY=.venv/Scripts/python.exe
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT

SL=$(oci network subnet get --subnet-id "$SUB" --query 'data."security-list-ids"[0]' --raw-output)
oci network security-list get --security-list-id "$SL" --query 'data."ingress-security-rules"' > "$tmp/in.json"
"$PY" -I - "$tmp/in.json" "$tmp/new.json" <<'EOF'
import json, sys
rules = json.load(open(sys.argv[1]))
if any((r.get("tcp-options") or {}).get("destination-port-range", {}).get("min") == 5432 for r in rules):
    print("правило 5432 вже є"); sys.exit(3)
rules.append({"source": "0.0.0.0/0", "protocol": "6", "is-stateless": False,
              "description": "ttc postgres trap",
              "tcp-options": {"destination-port-range": {"min": 5432, "max": 5432}}})
def camel(o):
    if isinstance(o, dict):
        return {"".join(w.capitalize() if i else w for i, w in enumerate(k.split("-"))): camel(v)
                for k, v in o.items()}
    return [camel(x) for x in o] if isinstance(o, list) else o
json.dump(camel(rules), open(sys.argv[2], "w"))
EOF
oci network security-list update --security-list-id "$SL" \
  --ingress-security-rules "file://$(cygpath -m "$tmp/new.json")" --force --query 'data."lifecycle-state"'
sleep 5
timeout 8 bash -c "</dev/tcp/${VM_HOST:?задай VM_HOST=<VM_HOST>}/5432" && echo "5432: OPEN" || echo "5432: ще закрито"
