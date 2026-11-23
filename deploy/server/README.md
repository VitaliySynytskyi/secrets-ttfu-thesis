# Колектор на Oracle Cloud Always Free

Мета: webhook-адреса, яка **не змінюється й працює 24/7** протягом усієї кампанії (тижні).
Адресу вписують у кожен Canarytoken під час створення, тож її зміна = втрачені сповіщення.

Вартість: 0 ₴ у межах Always Free (1 VM `VM.Standard.E2.1.Micro`, 50 ГБ boot-диск).
Банківська картка потрібна лише для верифікації під час реєстрації.

## 1. Акаунт Oracle Cloud

1. Зареєструватися на <https://signup.cloud.oracle.com>. **Home region** обрати
   ближчий (напр. `Germany Central (Frankfurt)`): змінити його потім неможливо, а Always Free-ресурси
   створюються лише в home region.
2. **Рекомендовано: перевести акаунт на Pay As You Go** (Billing → Upgrade and Manage Payment).
   Always Free-ресурси й після цього лишаються безкоштовними, але знімається політика
   *reclamation*: Oracle може зупинити Always Free-VM, якщо за 7 днів CPU (95-й перцентиль) і мережа
   < 20 %, а колектор якраз майже весь час простоює. Щоб не платити випадково — створювати
   **лише** ресурси з позначкою *Always Free-eligible* і поставити Budget alert на 1 USD
   (Billing → Budgets).

## 2. Віртуальна машина

Compute → Instances → Create instance:

- Image: **Canonical Ubuntu 24.04**;
- Shape: **VM.Standard.E2.1.Micro** (Always Free-eligible). Ampere A1 теж безкоштовний, але його
  часто немає в наявності («Out of capacity»), а колектору вистачає й micro;
- Networking: створити нову VCN з публічною підмережею, **Assign a public IPv4 address**;
- SSH keys: *Generate a key pair for me* → завантажити приватний ключ, зберегти як
  `~/.ssh/oci.key` (у Git Bash: `chmod 600 ~/.ssh/oci.key`).

Після створення записати **Public IP address**.

**Відкрити 80/443 у хмарному брандмауері:** Instance → Subnet → Security List → Add Ingress Rules:
Source `0.0.0.0/0`, TCP, Destination port `80,443`. (Брандмауер усередині ОС відкриє `setup.sh`.)

## 3. Домен (безкоштовно, DuckDNS)

Let's Encrypt не видає сертифікат на голу IP-адресу, тож потрібне ім'я.

1. <https://www.duckdns.org> → увійти через GitHub/Google → створити субдомен (далі — `<DOMAIN>`)
   → вказати в ньому Public IP з кроку 2. Записати **token** зі сторінки.
2. Перевага DuckDNS: якщо VM доведеться перестворити, достатньо змінити IP у DuckDNS —
   webhook-адреса у вже опублікованих токенах лишиться робочою.

## 4. Розгортання

З ноутбука (Git Bash, з кореня репозиторію):

```bash
bash deploy/server/push-code.sh ubuntu@<PUBLIC_IP>
ssh -i ~/.ssh/oci.key ubuntu@<PUBLIC_IP>
```

На VM:

```bash
DOMAIN=<DOMAIN> DUCKDNS_TOKEN=<DUCKDNS_TOKEN> bash /opt/ttc/app/deploy/server/setup.sh
```

Наприкінці скрипт друкує **webhook URL** вигляду `https://<DOMAIN>/canarytokens/<секрет>`.
Секретний сегмент шляху не дає стороннім підробити «влучання» (token_id легко вгадати).
URL не комітити й не публікувати.

Перевірка з ноутбука: `curl https://<DOMAIN>/healthz` → `{"status":"ok","tokens":0}`.

## 5. Моніторинг доступності

<https://uptimerobot.com> (безкоштовно): HTTP(s)-монітор на `https://<домен>/healthz` кожні 5 хв,
сповіщення на email. Якщо колектор впав — сповіщення Canarytokens за цей час дістаються
з історії токена на canarytokens.org (manage-сторінка) та з email-копій (див. `../README.md` §4).

## 6. Що де лежить на VM

| Шлях | Вміст |
|---|---|
| `/opt/ttc/app/data/ttc.db` | база кампанії (токени, влучання, події) |
| `/opt/ttc/app/data/raw-events.jsonl` | кожен вхідний payload **до** розбору — первинне джерело |
| `/opt/ttc/backups/` | щоденні знімки (03:15 UTC, зберігаються 30 днів) |
| `/etc/ttc/collector.env` | шлях до БД і секрет webhook |

Корисне: `sudo systemctl status ttc-collector`, `journalctl -u ttc-collector -f`,
`sudo tail -f /var/log/caddy/ttc-access.log`.

Оновлення коду: `push-code.sh` з ноутбука → на VM `sudo systemctl restart ttc-collector`.
Забрати дані на ноутбук: `bash deploy/server/pull-data.sh ubuntu@<PUBLIC_IP>` (раз на 1–2 дні).
