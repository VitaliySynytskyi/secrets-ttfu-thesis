"""Публікація пілотної honeytoken-кампанії: один токен = один публічний GitHub-репозиторій.

Для кожного token_id з плану (той самий зріз, що й `seed.py` на сервері):
  1. створює Canarytoken на canarytokens.org (memo `token_id=<id>`, webhook колектора);
  2. генерує правдоподібний маленький проєкт, де секрет розміщено за схемою канал × помітність;
  3. створює публічний репозиторій через `gh` і пушить;
  4. записує момент завершення пушу (= published_at) у маніфест.

Окремий репозиторій на токен — щоб один сканер, клонувавши репо, не «спрацьовував» на кілька
токенів одночасно (незалежність спостережень для аналізу виживаності).

Секрети, відповіді Canarytokens і робочі копії репозиторіїв лежать у ~/.config/ttc/ — поза
цим репозиторієм. Маніфест без секретів: ~/.config/ttc/published.csv.

    python deploy/publish_pilot.py --channels github dotenv --secret-types aws api --replicas 1 [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import secrets
import subprocess
import sys
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from collector.registry import CHANNELS, SECRET_TYPES, VISIBILITIES, build_plan  # noqa: E402

TTC_HOME = Path(os.environ.get("TTC_HOME", Path.home() / ".config" / "ttc"))
# Публічний endpoint генерації токенів сервісу canarytokens.org (не секрет); можна
# перевизначити для власного інстансу Canarytokens.
GENERATE_URL = os.environ.get("TTC_CANARY_GENERATE_URL",
                              "https://canarytokens.org/d3aece8093b71007b5ccfedad91ebb11/generate")
# `api`: canarytokens.org більше не видає slack_api, тож API-секрет — пара API_BASE_URL
# (URL-токен, спрацьовує при зверненні) + API_KEY (випадковий, для правдоподібності).
CANARY_TYPE = {"aws": "aws_keys", "api": "web"}

# Нейтральні назви проєктів — без слів «honeypot», «canary», «test».
# Публічна версія: назви-приклади, відмінні від використаних у реальному пілоті.
REPO_NAMES = {
    "github-aws-obvious": "example-sync",
    "github-aws-buried": "example-resizer",
    "github-api-obvious": "example-bot",
    "github-api-buried": "example-notifier",
    "dotenv-aws-obvious": "example-archive-api",
    "dotenv-aws-buried": "example-tracker",
    "dotenv-api-obvious": "example-digest",
    "dotenv-api-buried": "example-announcer",
}


def repo_name(token_id: str) -> str:
    base, replica = token_id.rsplit("-", 1)
    name = REPO_NAMES[base]
    return name if replica == "0" else f"{name}-{replica}"


# --------------------------------------------------------------------------- рендеринг

_ENV_FILLER = [
    ("APP_ENV", "production"), ("LOG_LEVEL", "info"), ("PORT", "8080"),
    ("DATABASE_HOST", "db.internal"), ("DATABASE_PORT", "5432"), ("DATABASE_NAME", "app"),
    ("DATABASE_USER", "app"), ("DATABASE_POOL_SIZE", "10"), ("REDIS_URL", "redis://cache:6379/0"),
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


def parse_args(argv=None):
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--limit", type=int, default=100)
    return p.parse_args(argv)
'''


def secret_pairs(secret_type: str, creds: dict) -> list[tuple[str, str]]:
    if secret_type == "aws":
        return [("AWS_ACCESS_KEY_ID", creds["aws_access_key_id"]),
                ("AWS_SECRET_ACCESS_KEY", creds["aws_secret_access_key"]),
                ("AWS_DEFAULT_REGION", creds.get("region") or "us-east-2")]
    return [("API_BASE_URL", creds["token_url"]), ("API_KEY", creds["api_key"])]


def render_repo(token_id: str, channel: str, secret_type: str, visibility: str,
                creds: dict) -> dict[str, str]:
    """Файли репозиторію {шлях: вміст}. Схема розміщення — deploy/README.md §2 і §4."""
    name = repo_name(token_id)
    pairs = secret_pairs(secret_type, creds)
    files = {"README.md": f"# {name}\n\nSmall internal utility. Run `python main.py`.\n"}
    lib = "boto3" if secret_type == "aws" else "requests"
    files["requirements.txt"] = "boto3\nrequests\n" if lib == "boto3" else "requests\n"

    if channel == "dotenv":
        if visibility == "obvious":
            files[".env"] = "".join(f"{k}={v}\n" for k, v in pairs)
        else:
            env = list(_ENV_FILLER)
            mid = len(env) // 2
            env[mid:mid] = pairs
            files[".env.example"] = "".join(f"{k}={v}\n" for k, v in env)
        files["main.py"] = ("import os\n\n\ndef main():\n"
                            "    cfg = {k: v for k, v in os.environ.items()}\n"
                            "    print(f\"loaded {len(cfg)} settings\")\n\n\n"
                            "if __name__ == \"__main__\":\n    main()\n")
        return files

    # channel == "github": секрет у коді
    if visibility == "obvious":
        header = "# AWS credentials\n" if secret_type == "aws" else "# API credentials\n"
        body = header + "".join(f'{k} = "{v}"\n' for k, v in pairs)
        files["main.py"] = (f"import {lib}\n\n"
                            + body + "\n\ndef main():\n    print(\"ok\")\n\n\n"
                            "if __name__ == \"__main__\":\n    main()\n")
    else:
        args = ", ".join(f'{k.lower()}="{v}"' for k, v in pairs)
        files["main.py"] = (f"import {lib}\n"
                            + _PY_FILLER
                            + f"\n\ndef make_client({args}):\n    return locals()\n"
                            + "\n\ndef main():\n    args = parse_args()\n"
                            "    client = make_client()\n"
                            "    for batch in chunked(list(range(args.limit)), 10):\n"
                            "        retry(lambda: len(batch))\n    print(bool(client))\n\n\n"
                            "if __name__ == \"__main__\":\n    main()\n")
    return files


# --------------------------------------------------------------------------- зовнішні дії

def create_canarytoken(token_id: str, secret_type: str, webhook_url: str) -> dict:
    boundary = uuid.uuid4().hex
    fields = {"token_type": CANARY_TYPE[secret_type], "memo": f"token_id={token_id}",
              "webhook_url": webhook_url}
    body = "".join(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n"
                   for k, v in fields.items()) + f"--{boundary}--\r\n"
    req = urllib.request.Request(GENERATE_URL, data=body.encode(), method="POST",
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.load(resp)
    if data.get("error"):
        raise RuntimeError(f"{token_id}: canarytokens error {data.get('error_message')}")
    if secret_type == "api":
        data["api_key"] = secrets.token_hex(20)
    return data


def _run(cmd: list[str], cwd: Path, check: bool = True) -> str:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[:3])} ...: exit {r.returncode}\n{r.stderr.strip()}")
    return r.stdout.strip()


def publish(repo_dir: Path, name: str, gh: str) -> tuple[str, datetime]:
    """Відновлюваний: повторний запуск пропускає вже зроблені кроки (git init, створення репо)."""
    login = _run([gh, "api", "user", "--jq", ".login"], repo_dir)
    uid = _run([gh, "api", "user", "--jq", ".id"], repo_dir)
    if not (repo_dir / ".git").exists():
        _run(["git", "init", "-b", "main"], repo_dir)
        _run(["git", "config", "user.name", login], repo_dir)
        _run(["git", "config", "user.email", f"{uid}+{login}@users.noreply.github.com"], repo_dir)
        # Лише для цього репо: скинути глобальні credential helpers (там може бути особистий
        # акаунт) і автентифікуватися токеном gh тестового акаунта.
        _run(["git", "config", "credential.helper", ""], repo_dir)
        gh_posix = gh.replace("\\", "/")
        _run(["git", "config", "--add", "credential.helper", f'!"{gh_posix}" auth git-credential'],
             repo_dir)
        _run(["git", "add", "-A"], repo_dir)
        _run(["git", "commit", "-m", "initial commit"], repo_dir)
    full = f"{login}/{name}"
    if _run([gh, "repo", "view", full, "--json", "name"], repo_dir, check=False) == "":
        _run([gh, "repo", "create", name, "--public", "--source", ".", "--remote", "origin"], repo_dir)
    if not _run(["git", "remote"], repo_dir):
        _run(["git", "remote", "add", "origin", f"https://github.com/{full}.git"], repo_dir)
    _run(["git", "push", "-u", "origin", "main"], repo_dir)
    pushed_at = datetime.now(timezone.utc).replace(microsecond=0)
    return f"https://github.com/{full}", pushed_at


# --------------------------------------------------------------------------- main

def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--channels", nargs="+", default=["github", "dotenv"], choices=CHANNELS)
    p.add_argument("--secret-types", nargs="+", default=["aws", "api"], choices=["aws", "api"])
    p.add_argument("--visibilities", nargs="+", default=list(VISIBILITIES), choices=VISIBILITIES)
    p.add_argument("--replicas", type=int, default=1)
    p.add_argument("--only", nargs="*", help="опублікувати лише ці token_id")
    p.add_argument("--gh", default="gh")
    p.add_argument("--dry-run", action="store_true", help="лише згенерувати файли з фіктивними ключами")
    a = p.parse_args(argv)

    webhook = (TTC_HOME / "webhook.env").read_text().strip().split("=", 1)[1] if not a.dry_run else ""
    manifest = TTC_HOME / "published.csv"
    done = set()
    if manifest.exists():
        done = {r["token_id"] for r in csv.DictReader(manifest.open(encoding="utf-8"))}

    plan = build_plan(replicas=a.replicas, channels=a.channels,
                      secret_types=a.secret_types, visibilities=a.visibilities)
    for tok in plan:
        if (a.only and tok.token_id not in a.only) or tok.token_id in done:
            continue
        name = repo_name(tok.token_id)
        repo_dir = TTC_HOME / "repos" / name
        if a.dry_run:
            creds = {"aws_access_key_id": "AKIAEXAMPLEEXAMPLE00", "region": "us-east-2",
                     "aws_secret_access_key": "x" * 40, "api_key": "0" * 40,
                     "token_url": "http://canarytokens.com/example/index.html"}
        else:
            tokfile = TTC_HOME / "tokens" / f"{tok.token_id}.json"
            if tokfile.exists():  # повторний запуск: не плодити нові Canarytokens
                creds = json.loads(tokfile.read_text())
            else:
                creds = create_canarytoken(tok.token_id, tok.secret_type, webhook)
                tokfile.parent.mkdir(parents=True, exist_ok=True)
                tokfile.write_text(json.dumps(creds, indent=1))
        repo_dir.mkdir(parents=True, exist_ok=True)
        for rel, content in render_repo(tok.token_id, tok.channel, tok.secret_type,
                                        tok.visibility, creds).items():
            (repo_dir / rel).write_text(content, encoding="utf-8", newline="\n")
        if a.dry_run:
            print(f"[dry-run] {tok.token_id} -> {repo_dir}")
            continue
        url, pushed_at = publish(repo_dir, name, a.gh)
        new = not manifest.exists()
        with manifest.open("a", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            if new:
                w.writerow(["token_id", "repo_url", "published_at", "canary_token"])
            w.writerow([tok.token_id, url, pushed_at.isoformat(), creds.get("token", "")])
        print(f"{tok.token_id}\t{url}\t{pushed_at.isoformat()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
