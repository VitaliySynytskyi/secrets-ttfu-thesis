#!/usr/bin/env bash
# Крок 1 (AWS): окремий member-акаунт для honeypot-ключів через AWS Organizations.
# Ізоляція: опубліковані ключі розкривають лише ID цього акаунта, а карантин AWS і
# support-кейси не зачіпають основний (лабораторний) акаунт.
#
# Запускає ВЛАСНИК акаунта (після `aws login --profile ttc-admin`):
#   bash deploy/cloud/aws-account.sh
# Ідемпотентний: якщо акаунт уже створено, лише дописує профіль ttc-hp.
set -euo pipefail
export AWS_PROFILE=${AWS_PROFILE:-ttc-admin}
export AWS_REGION=${AWS_REGION:-eu-central-1}
EMAIL=${TTC_AWS_EMAIL:?задай TTC_AWS_EMAIL=<AWS_ACCOUNT_EMAIL> — email root-користувача member-акаунта}
NAME=${TTC_AWS_ACCOUNT_NAME:-ttc-honeypot}

if ! aws organizations describe-organization >/dev/null 2>&1; then
  echo "Створюю AWS Organization (management = поточний акаунт)…"
  aws organizations create-organization --feature-set ALL >/dev/null
fi

acct=$(aws organizations list-accounts --query "Accounts[?Email=='$EMAIL'].Id" --output text)
if [ -z "$acct" ] || [ "$acct" = "None" ]; then
  echo "Створюю member-акаунт $NAME <$EMAIL>…"
  req=$(aws organizations create-account --email "$EMAIL" --account-name "$NAME" \
        --query 'CreateAccountStatus.Id' --output text)
  while :; do
    read -r state acct reason < <(aws organizations describe-create-account-status \
      --create-account-request-id "$req" \
      --query 'CreateAccountStatus.[State,AccountId,FailureReason]' --output text)
    [ "$state" = "IN_PROGRESS" ] || break
    sleep 10
  done
  [ "$state" = "SUCCEEDED" ] || { echo "Помилка створення акаунта: $reason" >&2; exit 1; }
fi
echo "Member-акаунт: $acct"

aws configure set region eu-central-1 --profile ttc-hp

# Root не може виконувати AssumeRole, тож OrganizationAccountAccessRole звідси недоступна.
# Доступ до member-акаунта — через його власний root: «Forgot password» на сторінці входу
# з адресою $EMAIL, після входу в консоль — `aws login --profile ttc-hp`.
cat <<EOF
Далі:
  1. https://signin.aws.amazon.com -> Root user -> $EMAIL -> Forgot password (лист прийде на цю адресу).
  2. Увійти в консоль member-акаунта $acct.
  3. aws login --profile ttc-hp
  4. bash deploy/cloud/aws-honeypot.sh
EOF
