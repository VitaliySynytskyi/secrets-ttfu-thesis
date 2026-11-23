#!/usr/bin/env bash
# Доступ до member-акаунта ttc-honeypot без його root.
# Root основного акаунта не може робити AssumeRole, тож заводимо IAM-користувача
# ttc-operator, який уміє лише одне: брати OrganizationAccountAccessRole у ttc-honeypot.
#
#   bash deploy/cloud/aws-operator.sh            (під профілем ttc-admin)
# Далі: увійти в консоль як ttc-operator -> `aws login --profile ttc-op` -> aws-honeypot.sh
set -euo pipefail
export AWS_PROFILE=${AWS_PROFILE:-ttc-admin}
export AWS_REGION=${AWS_REGION:-eu-central-1}
EMAIL=${TTC_AWS_EMAIL:?задай TTC_AWS_EMAIL=<AWS_ACCOUNT_EMAIL> (той самий, що в aws-account.sh)}
USER_NAME=ttc-operator

mgmt=$(aws sts get-caller-identity --query Account --output text)
member=$(aws organizations list-accounts --query "Accounts[?Email=='$EMAIL'].Id" --output text)
[ -n "$member" ] && [ "$member" != "None" ] || { echo "Спершу aws-account.sh" >&2; exit 1; }

aws iam get-user --user-name $USER_NAME >/dev/null 2>&1 || aws iam create-user --user-name $USER_NAME >/dev/null
aws iam put-user-policy --user-name $USER_NAME --policy-name assume-ttc-honeypot --policy-document "{
  \"Version\": \"2012-10-17\",
  \"Statement\": [{\"Effect\": \"Allow\", \"Action\": \"sts:AssumeRole\",
                   \"Resource\": \"arn:aws:iam::$member:role/OrganizationAccountAccessRole\"}]}"

# `aws login` для IAM-користувача потребує signin:AuthorizeOAuth2Access/CreateOAuth2Token.
aws iam attach-user-policy --user-name $USER_NAME \
  --policy-arn arn:aws:iam::aws:policy/SignInLocalDevelopmentAccess

if ! aws iam get-login-profile --user-name $USER_NAME >/dev/null 2>&1; then
  pw="Ttc-$(od -An -N12 -tx1 /dev/urandom | tr -d ' \n')!"
  aws iam create-login-profile --user-name $USER_NAME --password "$pw" --no-password-reset-required >/dev/null
  echo "Пароль консолі для $USER_NAME (збережи в менеджері паролів): $pw"
fi

aws configure set region eu-central-1 --profile ttc-op
aws configure set role_arn "arn:aws:iam::$member:role/OrganizationAccountAccessRole" --profile ttc-hp
aws configure set source_profile ttc-op --profile ttc-hp
aws configure set region eu-central-1 --profile ttc-hp

cat <<EOF

Далі:
  1. https://$mgmt.signin.aws.amazon.com/console  -> IAM user: $USER_NAME + пароль вище
  2. aws login --profile ttc-op
  3. bash deploy/cloud/aws-honeypot.sh
EOF
