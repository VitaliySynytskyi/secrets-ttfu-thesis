# secrets-ttfu-thesis

> **English summary.** Research code for the master's thesis *"Threat models and risk analysis
> for storing and using secrets in DevOps processes"* (Vitalii Synytskyi, Ivan Franko National
> University of Lviv, 2026). It contains (1) a local protection stand (kind + HashiCorp Vault +
> PostgreSQL) that demonstrates the move from static to short-lived dynamic secrets, (2) a
> measurement pipeline that publishes no-privilege decoy credentials (honeytokens) and records
> their first use through CloudTrail, GCP Cloud Audit Logs, a PostgreSQL trap and an API trap
> into a FastAPI + SQLite collector, and (3) survival analysis of time-to-first-use
> (Kaplan–Meier, log-rank, Cox, AIC-selected parametric models) that turns the fitted
> `F(TTL)` into a residual risk `F(TTL)·I` with bootstrap confidence intervals and the inverse
> task `TTL*`. Real campaign data is **not** included; a synthetic sample lets every step run.
> Code is MIT-licensed.

## Про репозиторій

Програмний код до кваліфікаційної роботи магістра:

- **Тема:** «Моделі загроз і аналіз ризиків при зберіганні та використанні секретів у DevOps-процесах».
- **Автор:** Віталій Синицький.
- **Науковий керівник:** доц. Михайло Павлик.
- **Заклад:** Львівський національний університет імені Івана Франка, спеціальність F3 «Комп'ютерні науки», 2026.

### Призначення

Код дає змогу відтворити емпіричну частину роботи: замість експертних оцінок імовірності
компрометації в матриці ризиків NIST SP 800-30 використати **виміряний** час до першого
використання (Time-To-First-Use, TTFU) витоку секрету. Для цього:

1. на стенді показано, що динамічні облікові дані з коротким TTL перестають працювати після
   закінчення терміну дії (захисний контур);
2. приманки-облікові дані без жодних прав публікуються в типові канали витоку (GitHub, `.env`
   у репозиторії, журнали CI/CD, paste-сервіси), а детектори фіксують момент першого
   використання (вимірювальний контур);
3. за отриманою вибіркою з цензуруванням оцінюються криві виживаності й залишковий ризик
   `R(TTL) = F(TTL) · I` для різних TTL (аналіз).

## Архітектура

```text
 Захисний контур (stand/)            Вимірювальний контур (collector/, deploy/)        Аналіз (modeling/, analysis/, calculator/)
 ┌──────────────────────────┐       ┌────────────────────────────────────────────┐     ┌──────────────────────────────────────────┐
 │ kind (Kubernetes)        │       │ приманки: AWS IAM-ключі, ключі GCP SA,      │     │ Каплан–Маєр, log-rank (канал, тип,       │
 │ HashiCorp Vault          │       │ облікові дані PostgreSQL, API-ключі —       │     │ помітність), модель Кокса                │
 │  - Kubernetes auth       │       │ без прав, у 4 каналах × 2 рівнях помітності │     │ Вейбулл / експоненційний / логнормальний │
 │  - Database secrets eng. │       │ детектори: CloudTrail, Cloud Audit Logs,    │ ──▶ │ (+ модель з часткою «невикористаних»),   │
 │ PostgreSQL               │       │ журнал Postgres-пастки, API-пастка,         │     │ вибір за AIC                             │
 │ сценарії 01–05: статичний│       │ вебхуки Canarytokens                        │     │ R(TTL) = F(TTL)·I, бутстреп-ДІ,          │
 │ секрет → динамічний, TTL │       │ колектор: FastAPI + SQLite (ttc.db) → CSV   │     │ обернена задача TTL* для R*              │
 └──────────────────────────┘       └────────────────────────────────────────────┘     └──────────────────────────────────────────┘
```

- **Захисний контур** — локальний стенд `stand/`: kind + Vault + PostgreSQL, сценарії
  відтворення від антипатерну зі статичним секретом до короткоживучих динамічних облікових
  даних, Vault Agent Injector, перевірки закінчення TTL та External Secrets Operator.
- **Вимірювальний контур** — колектор `collector/` (FastAPI-застосунок + SQLite-сховище
  `TtcStore`), опитувач хмарних журналів `collector/pollers.py` (AWS CloudTrail, GCP Cloud
  Audit Logs, csvlog Postgres-пастки), API-пастка (`/api-trap/*`) та адаптер вебхуків
  Canarytokens. Скрипти `deploy/` реєструють токени, генерують вміст приманок, публікують їх і
  експортують TTFU у CSV.
- **Аналіз** — `modeling/` (завантаження, підгонка розподілів, ризик, бутстреп),
  `analysis/analyze_campaign.py` (повний звіт: криві Каплана–Маєра, log-rank, Кокс, AIC,
  `F(TTL)·I`, `TTL*`), `analysis/power.py` (оцінка потужності), `calculator/cli.py`
  (наскрізний калькулятор залишкового ризику зі стратифікацією за каналом, типом секрету й
  помітністю).

## Структура каталогів

```text
analysis/        повний аналіз кампанії, проміжний звіт, оцінка потужності
calculator/      CLI калькулятора залишкового ризику та побудова кривої ризику
collector/       FastAPI-колектор, сховище SQLite, розбір хмарних журналів, опитувач
deploy/          реєстрація токенів, симуляція, генерація й публікація приманок, експорт
  cloud/         створення приманок в AWS / GCP і локальних облікових даних (БД, API)
  server/        розгортання колектора й пасток на VM (systemd, Caddy, Postgres-пастка)
modeling/        loader / survival / risk / exposure — статистичне ядро
tests/           pytest-тести (97)
data/sample/     синтетична вибірка (ttc.csv), згенерована simulate_campaign.py
docs/            провенанс літературних апріорних оцінок TTC (ttc-sources.md)
figures/         make_figures.py — рисунки роботи в стилі для друку
stand/           копія стенда kind + Vault + PostgreSQL (скрипти, Helm values, сценарії)
synthetic.py     генератор вибірок Вейбулла для тестів
```

Стенд `stand/` — копія відстежуваних файлів окремого репозиторію
[VitaliySynytskyi/coursework-stand](https://github.com/VitaliySynytskyi/coursework-stand)
(коміт `92f18b3`), включена, щоб цей репозиторій був самодостатнім.

## Вимоги

- Python **3.14** (код перевірено на 3.14.3; очікувано працює й на 3.11+), залежності — `requirements.txt`
  (fastapi, uvicorn, httpx, lifelines, scipy, numpy, pandas, matplotlib, pytest);
- для стенда: Docker, `kind`, `kubectl`, `helm`, `vault` CLI, Git Bash (на Windows);
- для розгортання колектора: VM з Ubuntu 22.04/24.04, доменне ім'я, AWS CLI / `gcloud` для
  створення приманок (необов'язково).

## Встановлення

```bash
git clone https://github.com/VitaliySynytskyi/secrets-ttfu-thesis.git
cd secrets-ttfu-thesis
python -m venv .venv
# Windows (Git Bash): .venv/Scripts/python.exe ; Linux/macOS: .venv/bin/python
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

Нижче `python` означає інтерпретатор із `.venv`. Усі команди запускаються з кореня репозиторію.

## Швидкий старт на синтетичних даних

1. **Симуляція кампанії** (96 токенів = 4 канали × 4 типи × 2 рівні помітності × 3 репліки;
   нічого не публікується, приманки випадкові й нефункціональні):

   ```bash
   python deploy/simulate_campaign.py --seed 20260627 --replicas 3 \
       --out data/sample/ttc.csv --manifest data/sim/manifest.csv --db data/sim/ttc-sim.db
   ```

   ```text
   Simulated 96 honeytokens (74 compromised, 22 censored).
   ```

   Файл `data/sample/ttc.csv` уже є в репозиторії (отриманий саме цією командою). Маніфест із
   випадковими значеннями-приманками навмисно не комітиться (`data/sim/` у `.gitignore`).

2. **Повний аналіз** (криві Каплана–Маєра, log-rank, Кокс, AIC, `F(TTL)·I`, `TTL*`):

   ```bash
   python -m analysis.analyze_campaign data/sample/ttc.csv --out data/sim/analysis \
       --label "СИНТЕТИЧНА вибірка" --n-boot 200
   ```

   Результат: `results.json`, `results.md`, `fig-km-channel.png`, `fig-km-type.png`, `fig-risk-ttl.png`.

   Фрагмент `results.md` для синтетичної вибірки (≈10 хв на ноутбуці, переважно бутстреп):

   ```text
   Токенів: 96, використано до кінця спостереження: 74.

   | Канал              | n  | використано | медіана      | частка за 1 год |
   | журнал CI/CD       | 24 | 21          | 12,4 хв      | 0,79            |
   | .env у репозиторії | 24 | 21          | 10,0 хв      | 0,88            |
   | GitHub             | 24 | 21          | 7,8 хв       | 0,83            |
   | paste-сервіс       | 24 | 11          | не досягнуто | 0,00            |

   log-rank: канал χ² = 29,25 (df = 3, p = 2e-06); тип секрету p = 0,39; помітність p = 0,18

   | Загроза                         | R калібр. (статичний, 30 діб) | R калібр. (TTL 60 с), 95 % ДІ | TTL* для R* = 0,05 |
   | T1. Витік через журнали CI/CD   | 0,700 (0,567–0,800)           | 0,004 (0,000–0,014)           | 2,7 хв             |
   | T2. Секрет у відкритому репоз.  | 0,831 (0,732–0,910)           | 0,007 (0,001–0,023)           | 2,0 хв             |
   ```


3. **Калькулятор залишкового ризику:**

   ```bash
   python -m calculator.cli data/sample/ttc.csv --ttl 15 --ttl 60 --impact 0.8 --out data/sim/report.json
   ```

   Фрагмент `report.json` (зведена вибірка, I = 0,8):

   ```json
   {
     "distribution": "lognormal_cure",
     "params": {"mu": 6.9378, "sigma": 1.9103, "cure": 0.2291},
     "aic": {"weibull": 1553.36, "exponential": 2158.84, "lognormal": 1519.15, "lognormal_cure": 1441.87},
     "residual_risk": {"15.0": 0.00827, "60.0": 0.04213},
     "monte_carlo": {"60.0": {"median": 0.04205, "ci_low": 0.00588, "ci_high": 0.13856}},
     "by_visibility": {"buried":  {"residual_risk": {"60.0": 0.03128}},
                       "obvious": {"residual_risk": {"60.0": 0.05290}}}
   }
   ```

   Звіт також містить стратифіковані підгонки `by_channel` і `by_secret_type`. Смуга
   `monte_carlo` — це лише чутливість до параметрів; статистично коректний довірчий інтервал
   дає бутстреп (`modeling.risk.bootstrap_residual_risk_ci`, використовується в
   `analysis.analyze_campaign`). Числа вище стосуються **синтетичної** вибірки й не є
   результатами роботи.

## Розгортання стенда

```bash
cd stand
cp .env.example .env.local          # задати POSTGRES_PASSWORD і VAULT_DEV_ROOT_TOKEN
bash scripts/up.sh                  # kind-кластер + Vault + PostgreSQL
bash scripts/smoke-test.sh
bash scenarios/01-static-secret-leak/reproduce.sh   # антипатерн: статичний секрет у журналі
bash scenarios/02-dynamic-short-lived/reproduce.sh  # динамічні облікові дані Vault
bash scenarios/03-sidecar-injector/reproduce.sh     # Vault Agent Injector, секрет у файлі
bash scenarios/04-ttl-expiry/reproduce.sh           # вхід після закінчення TTL відхиляється
bash scenarios/05-eso/reproduce.sh                  # External Secrets Operator
bash scripts/down.sh
```

Подробиці — `stand/README.md` і `stand/scenarios/*/README.md`.

## Розгортання колектора

Покроково — `deploy/README.md` (кампанія) і `deploy/server/README.md` (VM). Коротко:

```bash
# на ноутбуці
bash deploy/server/push-code.sh ubuntu@<VM_HOST>
# на VM
DOMAIN=<DOMAIN> DUCKDNS_TOKEN=<DUCKDNS_TOKEN> bash /opt/ttc/app/deploy/server/setup.sh
DOMAIN=<DOMAIN> bash /opt/ttc/app/deploy/server/traps-setup.sh   # Postgres- і API-пастки, опитувач
```

Локально без публікації: `python -m uvicorn collector.main:build_app --factory --port 8000`
або демонстрація вебхуків `python deploy/demo_webhook.py`.

Усі адреси, ідентифікатори й облікові дані задаються через змінні оточення або файли поза
репозиторієм (`$TTC_HOME`, за замовчуванням `~/.config/ttc/`):

| Змінна / файл | Призначення |
|---|---|
| `<VM_HOST>`, `VM_HOST` | публічна адреса VM колектора |
| `<DOMAIN>`, `DOMAIN` | доменне ім'я колектора (HTTPS через Caddy); API-пастка — `api.<DOMAIN>` |
| `DUCKDNS_TOKEN` | токен DuckDNS (необов'язково) |
| `TTC_DB_HOST`, `TTC_API_BASE` | хости Postgres- і API-пасток, що вписуються в приманки |
| `TTC_WEBHOOK_SECRET`, `TTC_DB`, `TTC_RAW_LOG`, `TTC_API_KEYS` | налаштування колектора (`/etc/ttc/collector.env`) |
| `TTC_AWS_EMAIL` (`<AWS_ACCOUNT_EMAIL>`), `TTC_ALERT_EMAIL` | email member-акаунта AWS і сповіщень бюджету |
| `TTC_GCP_PROJECT_PREFIX` | префікс ідентифікатора порожнього GCP-проєкту для приманок |
| `TTC_REPO_NAME_SALT` | ключ для генерації імен репозиторіїв-приманок |
| `TTC_CANARY_GENERATE_URL` | endpoint генерації Canarytokens (для власного інстансу) |
| `$TTC_HOME/oci-ids.env` | `SUB=<OCI_SUBNET_OCID>` для `oci-open-5432.sh` |
| `$TTC_HOME/{aws,gcp,db,api}/…` | ключі приманок і читачів журналів (ніколи не комітити) |

**Етика.** Публікувати можна лише приманки **без жодних прав**: IAM-користувачі AWS без
політик в ізольованому member-акаунті, сервісні акаунти GCP без ролей у проєкті без білінгу,
ролі PostgreSQL без `CONNECT`, API-ключі, що лише реєструють звернення. Обов'язково:
бюджетні ліміти й сповіщення (AWS Budgets на 1 USD), окремий тестовий акаунт для публікації,
погодження з керівником / етичним комітетом, жодних даних третіх осіб. Сирі журнали з IP-адресами
сканерів зберігаються лише локально й не публікуються.

## Тестування

```bash
python -m pytest -q
```

Результат на Windows 11, Python 3.14.3:

```text
97 passed, 44 warnings in 181.35s (0:03:01)
```

(Попередження — `DeprecationWarning` FastAPI щодо `asyncio.iscoroutinefunction` у Python 3.14.)

Тести не звертаються до мережі й хмарних сервісів; найдовший — бутстреп у `tests/test_risk.py` (≈2 хв).

## Відтворення рисунків

```bash
python figures/make_figures.py                          # на синтетичній вибірці data/sample/
python figures/make_figures.py data/campaign/<знімок>   # на власному знімку (ttc.csv / ttc-campaign.csv)
```

Рисунки (300 dpi, розміри під друк) пишуться у `figures/out/`. Скриншоти стенда не
генеруються; скрипт пропускає їх, якщо файлів немає. Рисунки, побудовані на `data/sample/`,
ілюструють лише вигляд графіків — числа роботи отримано на реальній вибірці, яка до
репозиторію не входить.

## Етичні застереження й обмеження

- **Реальних даних кампанії тут немає.** База колектора, сирі журнали, знімки, маніфести
  публікації та ключі приманок вилучені: вони містять облікові дані-приманки, ідентифікатори
  хмарних акаунтів та IP-адреси сканерів, а кампанія на момент публікації коду ще триває.
  Імена приманок (IAM-користувачі, сервісні акаунти, ролі БД, репозиторії) та адреси
  інфраструктури в коді замінено на приклади або змінні оточення.
- Синтетична вибірка відтворює лише форму даних; її параметри — апріорні оцінки з літератури
  (`docs/ttc-sources.md`), а не результати.
- Обмеження методики (цензурування, стратифікація, зовнішня валідність, різниця між
  бутстреп-ДІ та смугою чутливості) описані в тексті роботи.
- Код призначено для досліджень захисту; використовувати його для доступу до чужих систем заборонено.

## Використання ШІ-інструментів

Під час розроблення коду й документації використовувалися ШІ-асистенти (Claude, Anthropic),
що відповідає декларації в тексті роботи. Архітектуру, методику, перевірку результатів і
висновки виконано та верифіковано автором.

## Ліцензія

[MIT](LICENSE) © 2026 Vitalii Synytskyi.

## Цитування

Синицький В. В. Моделі загроз і аналіз ризиків при зберіганні та використанні секретів у
DevOps-процесах : кваліфікаційна робота магістра : спец. F3 Комп'ютерні науки ; наук. кер.
М. Павлик. Львів, 2026.

Код: Синицький В. В. secrets-ttfu-thesis : програмний код до кваліфікаційної роботи магістра.
2026. URL: https://github.com/VitaliySynytskyi/secrets-ttfu-thesis.
