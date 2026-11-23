"""Генерація вмісту honeytoken-артефактів (чисті функції, без мережі) для 4 каналів × 4 типів.

Секрет розміщується за схемою канал × помітність (deploy/README.md §4):
  github  — у коді репозиторію;
  dotenv  — у .env (obvious) / посеред великого .env.example (buried);
  ci-log  — НЕ в коді: значення йде в repo variables, workflow друкує його в публічний лог;
  paste   — текст публічної пасти.
obvious: явний, підписаний патерн; buried: те саме значення без маркера, серед звичайного вмісту.

Типи секретів нормалізуються у SecretSpec: pairs (env-style key=value), files (окремі файли,
напр. JSON ключа GCP), primary (заголовний секрет для obvious-підпису в paste/ci-log).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

# Хости пасток (Postgres-пастка і API-пастка) задаються оточенням; реальні адреси кампанії
# у публічну версію коду не входять. Див. README, розділ «Розгортання колектора».
DB_HOST = os.environ.get("TTC_DB_HOST", "db.example.invalid")
API_BASE = os.environ.get("TTC_API_BASE", "https://api.example.invalid")

_ENV_FILLER = [
    ("APP_ENV", "production"), ("LOG_LEVEL", "info"), ("PORT", "8080"),
    ("DATABASE_POOL_SIZE", "10"), ("REDIS_URL", "redis://cache:6379/0"),
    ("CACHE_TTL_SECONDS", "300"), ("SESSION_COOKIE_NAME", "sid"), ("CORS_ORIGINS", "*"),
    ("SENTRY_ENVIRONMENT", "production"), ("FEATURE_NEW_CHECKOUT", "false"),
    ("WORKER_CONCURRENCY", "4"), ("QUEUE_NAME", "default"), ("TZ", "UTC"),
    ("HTTP_TIMEOUT_SECONDS", "15"), ("RATE_LIMIT_PER_MINUTE", "120"), ("METRICS_ENABLED", "true"),
    ("SMTP_HOST", "smtp.internal"), ("SMTP_PORT", "587"), ("MAIL_FROM", "noreply@example.org"),
    ("UPLOAD_MAX_MB", "25"), ("DEFAULT_LOCALE", "en"), ("HEALTHCHECK_PATH", "/healthz"),
]

_PY_FILLER = '''

def chunked(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def retry(fn, attempts=3):
    last = None
    for _ in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last = exc
    raise last
'''


@dataclass
class SecretSpec:
    pairs: list[tuple[str, str]] = field(default_factory=list)
    files: dict[str, str] = field(default_factory=dict)
    primary: tuple[str, str] = ("", "")   # (label, value) — заголовний секрет


def secret_spec(secret_type: str, creds: dict) -> SecretSpec:
    if secret_type == "aws":
        pairs = [("AWS_ACCESS_KEY_ID", creds["aws_access_key_id"]),
                 ("AWS_SECRET_ACCESS_KEY", creds["aws_secret_access_key"]),
                 ("AWS_DEFAULT_REGION", creds.get("region", "eu-central-1"))]
        return SecretSpec(pairs=pairs, primary=("AWS_SECRET_ACCESS_KEY", creds["aws_secret_access_key"]))
    if secret_type == "db":
        url = creds["database_url"]
        return SecretSpec(pairs=[("DATABASE_URL", url)], primary=("DATABASE_URL", url))
    if secret_type == "api":
        pairs = [("API_BASE_URL", creds["api_base_url"]), ("API_KEY", creds["api_key"])]
        return SecretSpec(pairs=pairs, primary=("API_KEY", creds["api_key"]))
    if secret_type == "gcp":
        content = creds["key_json"]
        return SecretSpec(pairs=[("GOOGLE_APPLICATION_CREDENTIALS", "service-account.json")],
                          files={"service-account.json": content},
                          primary=("service-account.json", content))
    raise ValueError(f"unknown secret_type {secret_type}")


# --------------------------------------------------------------------------- github (у коді)

def _py_obvious(spec: SecretSpec, secret_type: str) -> dict[str, str]:
    files = dict(spec.files)
    if spec.files:  # gcp: ключ у файлі, код його читає з явним коментарем
        files["main.py"] = ("import json\n\n"
                            "# service account credentials\n"
                            'CREDENTIALS_FILE = "service-account.json"\n\n\n'
                            "def main():\n"
                            "    creds = json.load(open(CREDENTIALS_FILE))\n"
                            '    print("loaded", creds["client_email"])\n\n\n'
                            'if __name__ == "__main__":\n    main()\n')
        return files
    lib = "boto3" if secret_type == "aws" else "requests"
    header = {"aws": "# AWS credentials\n", "db": "# database connection\n",
              "api": "# API credentials\n"}[secret_type]
    body = header + "".join(f'{k} = "{v}"\n' for k, v in spec.pairs)
    files["main.py"] = (f"import {lib}\n\n" + body
                        + '\n\ndef main():\n    print("ok")\n\n\n'
                        'if __name__ == "__main__":\n    main()\n')
    return files


def _py_buried(spec: SecretSpec, secret_type: str) -> dict[str, str]:
    files = dict(spec.files)
    if spec.files:  # gcp: ключ як невиразно названий конфіг, шлях вписано в код без маркера
        files.pop("service-account.json")
        files["config/client.json"] = spec.files["service-account.json"]
        files["main.py"] = ("import json\n" + _PY_FILLER
                            + '\n\ndef load(path="config/client.json"):\n'
                            "    return json.load(open(path))\n\n\n"
                            "def main():\n    cfg = load()\n"
                            "    for batch in chunked(list(range(50)), 10):\n"
                            "        retry(lambda: len(batch))\n    print(bool(cfg))\n\n\n"
                            'if __name__ == "__main__":\n    main()\n')
        return files
    lib = "boto3" if secret_type == "aws" else "requests"
    args = ", ".join(f'{k.lower()}="{v}"' for k, v in spec.pairs)
    files["main.py"] = (f"import {lib}\n" + _PY_FILLER
                        + f"\n\ndef make_client({args}):\n    return locals()\n\n\n"
                        "def main():\n    client = make_client()\n"
                        "    for batch in chunked(list(range(50)), 10):\n"
                        "        retry(lambda: len(batch))\n    print(bool(client))\n\n\n"
                        'if __name__ == "__main__":\n    main()\n')
    return files


# --------------------------------------------------------------------------- dotenv

def _dotenv(spec: SecretSpec, visibility: str) -> dict[str, str]:
    files = dict(spec.files)
    if visibility == "obvious":
        files[".env"] = "".join(f"{k}={v}\n" for k, v in spec.pairs)
    else:
        env = list(_ENV_FILLER)
        mid = len(env) // 2
        env[mid:mid] = spec.pairs
        files[".env.example"] = "".join(f"{k}={v}\n" for k, v in env)
        if "service-account.json" in files:  # приховати й сам файл ключа
            files["config/client.json"] = files.pop("service-account.json")
            files[".env.example"] = files[".env.example"].replace(
                "GOOGLE_APPLICATION_CREDENTIALS=service-account.json",
                "GOOGLE_APPLICATION_CREDENTIALS=config/client.json")
    files["main.py"] = ("import os\n\n\ndef main():\n"
                        "    print(len(os.environ), 'settings')\n\n\n"
                        'if __name__ == "__main__":\n    main()\n')
    return files


# --------------------------------------------------------------------------- ci-log (лог Actions)

def ci_variables(spec: SecretSpec) -> dict[str, str]:
    """Значення, які кладуться в repo variables (НЕ у файли). GCP-ключ — одним рядком JSON."""
    if spec.files:
        return {"GCP_SA_JSON": spec.primary[1]}
    return {k: v for k, v in spec.pairs}


def ci_workflow(spec: SecretSpec, visibility: str) -> dict[str, str]:
    """Файли репозиторію ci-log. Секрет лише в ${{ vars.* }}; змінні не маскуються в логах."""
    varnames = list(ci_variables(spec))
    if visibility == "obvious":
        lines = "\n".join(f'          echo "{n}=${{{{ vars.{n} }}}}"' for n in varnames)
        step = f"      - name: Configure\n        run: |\n          echo \"Setting up deploy\"\n{lines}\n"
    else:
        env = "\n".join(f"          {n}: ${{{{ vars.{n} }}}}" for n in varnames)
        step = ("      - name: Environment\n        run: printenv | sort\n"
                f"        env:\n{env}\n")
    wf = ("name: deploy\non:\n  push:\n    branches: [main]\n  workflow_dispatch:\n\n"
          "jobs:\n  deploy:\n    runs-on: ubuntu-latest\n    steps:\n"
          "      - uses: actions/checkout@v4\n" + step)
    return {".github/workflows/deploy.yml": wf,
            "README.md": "# deploy-pipeline\n\nCI deployment configuration.\n"}


# --------------------------------------------------------------------------- paste

def paste_content(spec: SecretSpec, visibility: str) -> tuple[str, str, str]:
    """(title, body, format) публічної пасти."""
    if spec.files:  # gcp: сам JSON ключа
        if visibility == "obvious":
            return ("service-account.json", spec.primary[1], "json")
        import json as _json
        wrapper = {"version": 2, "runtime": "python3.11", "region": "eu-central-1",
                   "env": {"LOG_LEVEL": "info"}, "credentials": _json.loads(spec.primary[1]),
                   "scaling": {"min": 1, "max": 5}}
        return ("app config", _json.dumps(wrapper, indent=2), "json")
    if visibility == "obvious":
        body = "# deployment credentials\n" + "\n".join(f"{k}={v}" for k, v in spec.pairs)
        return ("deploy.env", body, "ini")
    env = list(_ENV_FILLER)
    mid = len(env) // 2
    env[mid:mid] = spec.pairs
    return ("config dump", "\n".join(f"{k}={v}" for k, v in env), "ini")


# --------------------------------------------------------------------------- диспетчер

def render(channel: str, secret_type: str, visibility: str, creds: dict):
    """github/dotenv/ci-log -> {path: content}; paste -> (title, body, format)."""
    spec = secret_spec(secret_type, creds)
    if channel == "github":
        return _py_obvious(spec, secret_type) if visibility == "obvious" \
            else _py_buried(spec, secret_type)
    if channel == "dotenv":
        return _dotenv(spec, visibility)
    if channel == "ci-log":
        return ci_workflow(spec, visibility)
    if channel == "paste":
        return paste_content(spec, visibility)
    raise ValueError(f"unknown channel {channel}")
