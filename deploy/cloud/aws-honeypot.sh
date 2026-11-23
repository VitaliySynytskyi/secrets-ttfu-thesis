#!/usr/bin/env bash
# Крок 2 (AWS): honeypot-ключі в member-акаунті ttc-hp (після aws-account.sh).
#
#  * по одному IAM-користувачу на кожен aws-токен основної кампанії (репліки 1-3:
#    4 канали x 2 помітності x 3 = 24) + calib-aws-0 для калібрування затримки;
#    жодних політик => ключ нічого не може, але кожен виклик (навіть GetCallerIdentity,
#    якому права не потрібні) потрапляє в CloudTrail event history;
#  * імена користувачів нейтральні (svc-*), бо GetCallerIdentity показує їх атакувальнику;
#  * користувач cloudtrail-reader з правом лише на cloudtrail:LookupEvents/ec2:DescribeRegions
#    — його ключ живе на VM і опитує журнал;
#  * бюджет 1 USD зі сповіщенням на email.
#
# Секрети — лише в ~/.config/ttc/aws/ (поза репозиторієм).
#   bash deploy/cloud/aws-honeypot.sh
# Ідемпотентний: наявних користувачів/ключів не чіпає.
set -euo pipefail
export AWS_PROFILE=${AWS_PROFILE:-ttc-hp}
export AWS_REGION=${AWS_REGION:-eu-central-1}
EMAIL=${TTC_ALERT_EMAIL:?задай TTC_ALERT_EMAIL=<ALERT_EMAIL> для сповіщень бюджету}
OUT=${TTC_HOME:-$HOME/.config/ttc}/aws
mkdir -p "$OUT/keys" && chmod 700 "$OUT"
acct=$(aws sts get-caller-identity --query Account --output text)
echo "Акаунт: $acct"

# Публічна версія: імена-приклади (у реальній кампанії використано інший набір).
APPS=(app-01 app-02 app-03 app-04 app-05 app-06 app-07 app-08 app-09 app-10 app-11 app-12
      app-13 app-14 app-15 app-16 app-17 app-18 app-19 app-20 app-21 app-22 app-23 app-24 app-25)

tokens=()
for ch in github ci-log paste dotenv; do
  for vis in obvious buried; do
    for r in 1 2 3; do tokens+=("$ch-aws-$vis-$r"); done
  done
done
tokens+=(calib-aws-0)

map=$OUT/users.csv
[ -f "$map" ] || echo "token_id,user_name,access_key_id" > "$map"
i=0
for tok in "${tokens[@]}"; do
  user="svc-${APPS[$i]}"; i=$((i + 1))
  keyfile=$OUT/keys/$tok.json
  [ -f "$keyfile" ] && continue
  aws iam get-user --user-name "$user" >/dev/null 2>&1 || aws iam create-user --user-name "$user" >/dev/null
  # через тимчасовий файл: якщо виклик упаде, порожній keyfile не «заблокує» повторний запуск
  aws iam create-access-key --user-name "$user" --output json > "$keyfile.tmp"
  mv "$keyfile.tmp" "$keyfile"
  chmod 600 "$keyfile"
  kid=$(sed -n 's/.*"AccessKeyId": "\([^"]*\)".*/\1/p' "$keyfile")
  echo "$tok,$user,$kid" >> "$map"
  echo "  $tok -> $user ($kid)"
done

# --- читач CloudTrail для VM ---
reader=cloudtrail-reader
aws iam get-user --user-name $reader >/dev/null 2>&1 || aws iam create-user --user-name $reader >/dev/null
aws iam put-user-policy --user-name $reader --policy-name lookup-only --policy-document '{
  "Version": "2012-10-17",
  "Statement": [{"Effect": "Allow",
                 "Action": ["cloudtrail:LookupEvents", "ec2:DescribeRegions"],
                 "Resource": "*"}]}'
if [ ! -f "$OUT/reader.env" ]; then
  read -r kid secret < <(aws iam create-access-key --user-name $reader \
    --query 'AccessKey.[AccessKeyId,SecretAccessKey]' --output text)
  printf 'AWS_ACCESS_KEY_ID=%s\nAWS_SECRET_ACCESS_KEY=%s\nTTC_AWS_ACCOUNT=%s\n' \
    "$kid" "$secret" "$acct" > "$OUT/reader.env"
  chmod 600 "$OUT/reader.env"
fi

# --- бюджет 1 USD ---
if ! aws budgets describe-budget --account-id "$acct" --budget-name ttc-1usd >/dev/null 2>&1; then
  aws budgets create-budget --account-id "$acct" \
    --budget '{"BudgetName":"ttc-1usd","BudgetLimit":{"Amount":"1","Unit":"USD"},"TimeUnit":"MONTHLY","BudgetType":"COST"}' \
    --notifications-with-subscribers "[{\"Notification\":{\"NotificationType\":\"ACTUAL\",\"ComparisonOperator\":\"GREATER_THAN\",\"Threshold\":10,\"ThresholdType\":\"PERCENTAGE\"},\"Subscribers\":[{\"SubscriptionType\":\"EMAIL\",\"Address\":\"$EMAIL\"}]}]"
fi
echo "Готово: $(($(wc -l < "$map") - 1)) ключів у $OUT/keys, читач у $OUT/reader.env"
