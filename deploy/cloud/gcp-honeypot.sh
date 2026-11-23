#!/usr/bin/env bash
# GCP: порожній проєкт із honeypot-ключами сервісних акаунтів (після `gcloud auth login`).
#
#  * проєкт без білінгу => витратити гроші неможливо в принципі;
#  * по сервісному акаунту без жодних ролей на кожен gcp-токен основної кампанії
#    (4 канали x 2 помітності x 3 репліки = 24) + calib-gcp-0; імена нейтральні;
#  * увімкнені Data Access audit logs для всіх сервісів (ADMIN_READ/DATA_READ/DATA_WRITE),
#    щоб відмови в доступі теж потрапляли в журнал;
#  * сервісний акаунт log-reader (roles/logging.privateLogViewer) — його ключ живе на VM;
#  * політику Google щодо витоку ключів (за замовчуванням DISABLE_KEY) НЕ змінюємо:
#    автовимкнення ключа фіксуємо як подію `exposed`.
#
# Секрети — лише в ~/.config/ttc/gcp/ (поза репозиторієм).
#   bash deploy/cloud/gcp-honeypot.sh
# Ідемпотентний: наявні акаунти/ключі не чіпає.
set -euo pipefail
GCLOUD=${GCLOUD:-"$(cygpath "${LOCALAPPDATA:-}")/Google/Cloud SDK/google-cloud-sdk/bin/gcloud"}
[ -x "$GCLOUD" ] || GCLOUD=gcloud
g() { "$GCLOUD" --quiet "$@"; }
HERE=$(cd "$(dirname "$0")" && pwd)
PY=${PY:-"$HERE/../../.venv/Scripts/python.exe"}
OUT=${TTC_HOME:-$HOME/.config/ttc}/gcp
mkdir -p "$OUT/keys" && chmod 700 "$OUT"

if [ -f "$OUT/project" ]; then
  PROJECT=$(cat "$OUT/project")
else
  PREFIX=${TTC_GCP_PROJECT_PREFIX:?задай TTC_GCP_PROJECT_PREFIX=<GCP_PROJECT_PREFIX>, напр. my-app}
  PROJECT=$PREFIX-$(od -An -N3 -tx1 /dev/urandom | tr -d ' \n')
  g projects create "$PROJECT" --name "$PREFIX"
  echo "$PROJECT" > "$OUT/project"
fi
echo "Проєкт: $PROJECT"
g services enable iam.googleapis.com logging.googleapis.com cloudresourcemanager.googleapis.com \
  --project "$PROJECT"

# --- читач журналу для VM (створюємо першим, щоб виключити його з аудиту нижче) ---
reader=log-reader@$PROJECT.iam.gserviceaccount.com
g iam service-accounts describe "$reader" --project "$PROJECT" >/dev/null 2>&1 \
  || g iam service-accounts create log-reader --project "$PROJECT"

# --- Data Access audit logs для всіх сервісів; власні читання log-reader не логуються,
#     інакше кожне опитування журналу (раз на хвилину) само створювало б запис ---
g projects get-iam-policy "$PROJECT" --format=json > "$OUT/policy.json"
"$PY" -I - "$OUT/policy.json" "serviceAccount:$reader" <<'EOF'
import json, sys
p = json.load(open(sys.argv[1]))
p["auditConfigs"] = [{"service": "allServices", "auditLogConfigs": [
    {"logType": "ADMIN_READ"}, {"logType": "DATA_WRITE"},
    {"logType": "DATA_READ", "exemptedMembers": [sys.argv[2]]}]}]
json.dump(p, open(sys.argv[1], "w"))
EOF
g projects set-iam-policy "$PROJECT" "$OUT/policy.json" --format=none
rm -f "$OUT/policy.json"

# Публічна версія: імена-приклади (у реальній кампанії використано інший набір).
APPS=(sa-app-01 sa-app-02 sa-app-03 sa-app-04 sa-app-05 sa-app-06 sa-app-07 sa-app-08
      sa-app-09 sa-app-10 sa-app-11 sa-app-12 sa-app-13 sa-app-14 sa-app-15 sa-app-16
      sa-app-17 sa-app-18 sa-app-19 sa-app-20 sa-app-21 sa-app-22 sa-app-23 sa-app-24 sa-app-25)

tokens=()
for ch in github ci-log paste dotenv; do
  for vis in obvious buried; do
    for r in 1 2 3; do tokens+=("$ch-gcp-$vis-$r"); done
  done
done
tokens+=(calib-gcp-0)

map=$OUT/accounts.csv
[ -f "$map" ] || echo "token_id,sa_email,key_id" > "$map"
i=0
for tok in "${tokens[@]}"; do
  sa=${APPS[$i]}; i=$((i + 1))
  email="$sa@$PROJECT.iam.gserviceaccount.com"
  keyfile=$OUT/keys/$tok.json
  [ -s "$keyfile" ] && continue
  rm -f "$keyfile"
  g iam service-accounts describe "$email" --project "$PROJECT" >/dev/null 2>&1 \
    || g iam service-accounts create "$sa" --project "$PROJECT" --display-name "$sa"
  # новий акаунт стає видимим для keys create із затримкою (eventual consistency)
  for attempt in 1 2 3 4 5 6; do
    if g iam service-accounts keys create "$keyfile.tmp" --iam-account "$email" \
         --project "$PROJECT" 2>/dev/null; then break; fi
    rm -f "$keyfile.tmp"
    [ "$attempt" = 6 ] && { echo "Не вдалося створити ключ для $email" >&2; exit 1; }
    sleep 10
  done
  mv "$keyfile.tmp" "$keyfile"
  chmod 600 "$keyfile"
  kid=$("$PY" -I -c "import json,sys;print(json.load(open(sys.argv[1]))['private_key_id'])" "$keyfile")
  echo "$tok,$email,$kid" >> "$map"
  echo "  $tok -> $email ($kid)"
done

# --- права читача ---
g projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:$reader" \
  --role roles/logging.privateLogViewer --condition=None --format=none
if [ ! -s "$OUT/reader.json" ]; then
  g iam service-accounts keys create "$OUT/reader.json.tmp" --iam-account "$reader" --project "$PROJECT"
  mv "$OUT/reader.json.tmp" "$OUT/reader.json"; chmod 600 "$OUT/reader.json"
fi
echo "Готово: $(($(wc -l < "$map") - 1)) ключів у $OUT/keys, читач у $OUT/reader.json"
