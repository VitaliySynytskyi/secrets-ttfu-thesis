"""Публікація основної кампанії (96 honeytoken-ів, репліки 1-3) по 4 каналах × 4 типах.

Секрети — справжні облікові дані БЕЗ прав (deploy/cloud/*): вони лише сигналізують про
звернення й не дають доступу. Кожен — у своє публічне місце; окремий репозиторій на токен
забезпечує незалежність спостережень (один сканер, клонувавши репо, не «засвічує» кілька).

Канали:
  github / dotenv / ci-log — публічний репозиторій тестового акаунта (gh);
  paste                    — публічна паста на pastebin.com.
published_at: час пушу (git), завершення прогону workflow (ci-log), відповіді API (paste).

Маніфест без секретів: ~/.config/ttc/campaign-published.csv (token_id,channel,visibility,
secret_type,location,published_at). Повторний запуск пропускає вже опубліковані — тож
кампанію можна лити хвилями:  python deploy/publish_campaign.py --limit 12 --pause 240

    python deploy/publish_campaign.py --dry-run                 # згенерувати, нічого не слати
    python deploy/publish_campaign.py --channels github dotenv  # лише частина
    python deploy/publish_campaign.py --only github-aws-obvious-1
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import random
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from collector.registry import CHANNELS, SECRET_TYPES, VISIBILITIES, build_plan  # noqa: E402
from deploy.campaign_render import API_BASE, DB_HOST, ci_variables, render, secret_spec  # noqa: E402
from deploy.publish_pilot import _run  # noqa: E402

TTC_HOME = Path(os.environ.get("TTC_HOME", Path.home() / ".config" / "ttc"))
MANIFEST = TTC_HOME / "campaign-published.csv"
PASTEBIN_URL = "https://pastebin.com/api/api_post.php"
DPASTE_URL = "https://dpaste.com/api/v2/"
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/129.0 Safari/537.36")

# Публічна версія: списки слів і ключ імен (TTC_REPO_NAME_SALT) навмисно відрізняються від
# використаних у реальній кампанії, щоб імена репозиторіїв-приманок не можна було відтворити.
REPO_NAME_SALT = os.environ.get("TTC_REPO_NAME_SALT", "change-me")
_ADJ = ("alpha bravo delta echo gamma kappa lambda omega sigma theta "
        "north south east west upper lower inner outer prime core").split()
_NOUN = ("service tool app util module client agent daemon task job "
         "runner handler adapter connector helper").split()


def repo_name(token_id: str) -> str:
    """Нейтральне, детерміноване й унікальне ім'я репозиторію. Суфікс-хеш (HMAC з ключем
    TTC_REPO_NAME_SALT) гарантує відсутність колізій (слова лише для правдоподібності)."""
    import hashlib
    import hmac
    digest = hmac.new(REPO_NAME_SALT.encode(), token_id.encode(), hashlib.sha256).hexdigest()
    h = int(digest, 16)
    return f"{_ADJ[h % len(_ADJ)]}-{_NOUN[(h // len(_ADJ)) % len(_NOUN)]}-{digest[:6]}"


# --------------------------------------------------------------------------- облікові дані

def _csv_lookup(path: Path, token_id: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["token_id"] == token_id:
                return r
    raise KeyError(f"{token_id} не знайдено в {path}")


def load_creds(token_id: str, secret_type: str) -> dict:
    if secret_type == "aws":
        d = json.loads((TTC_HOME / "aws" / "keys" / f"{token_id}.json").read_text())["AccessKey"]
        return {"aws_access_key_id": d["AccessKeyId"],
                "aws_secret_access_key": d["SecretAccessKey"], "region": "eu-central-1"}
    if secret_type == "gcp":
        return {"key_json": (TTC_HOME / "gcp" / "keys" / f"{token_id}.json").read_text()}
    if secret_type == "db":
        r = _csv_lookup(TTC_HOME / "db" / "creds.csv", token_id)
        return {"database_url": f"postgresql://{r['user']}:{r['password']}@{DB_HOST}:5432/app"}
    if secret_type == "api":
        r = _csv_lookup(TTC_HOME / "api" / "keys.csv", token_id)
        return {"api_base_url": API_BASE, "api_key": r["api_key"]}
    raise ValueError(secret_type)


# --------------------------------------------------------------------------- живі дії

def _write_repo(repo_dir: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        p = repo_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8", newline="\n")


def _gh_disable_push_protection(full: str, gh: str, repo_dir: Path) -> None:
    body = '{"security_and_analysis":{"secret_scanning_push_protection":{"status":"disabled"}}}'
    r = subprocess.run([gh, "api", "--method", "PATCH", f"repos/{full}", "--input", "-"],
                       input=body, cwd=repo_dir, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(f"  (push protection на {full} не вимкнено: {r.stderr.strip().splitlines()[-1:]})",
              file=sys.stderr)
    time.sleep(2)  # коротка пауза на поширення налаштування


def _git_push(repo_dir: Path, name: str, gh: str) -> tuple[str, str, datetime]:
    """Створити публічний репо тестового акаунта й запушити. Перед пушем вимикає push
    protection САМЕ на цьому репо — інакше GitHub блокує коміт honeytoken-а (його публікація
    і є метою); стороннє сканування секретів, яке ми вимірюємо, це не вимикає. Відновлюваний:
    повторний запуск пропускає вже зроблені кроки."""
    login = _run([gh, "api", "user", "--jq", ".login"], repo_dir)
    uid = _run([gh, "api", "user", "--jq", ".id"], repo_dir)
    if not (repo_dir / ".git").exists():
        _run(["git", "init", "-b", "main"], repo_dir)
        _run(["git", "config", "user.name", login], repo_dir)
        _run(["git", "config", "user.email", f"{uid}+{login}@users.noreply.github.com"], repo_dir)
        _run(["git", "config", "credential.helper", ""], repo_dir)
        gh_posix = gh.replace("\\", "/")
        _run(["git", "config", "--add", "credential.helper",
              f'!"{gh_posix}" auth git-credential'], repo_dir)
        _run(["git", "add", "-A"], repo_dir)
        _run(["git", "commit", "-m", "initial commit"], repo_dir)
    full = f"{login}/{name}"
    if _run([gh, "repo", "view", full, "--json", "name"], repo_dir, check=False) == "":
        _run([gh, "repo", "create", name, "--public", "--source", ".", "--remote", "origin"], repo_dir)
    if not _run(["git", "remote"], repo_dir):
        _run(["git", "remote", "add", "origin", f"https://github.com/{full}.git"], repo_dir)
    # Вимкнути push protection саме на цьому репо (коректний JSON через stdin --input -).
    # Якщо push protection увімкнено ще й на рівні акаунта («Push protection for yourself»),
    # цього недостатньо — вимкнути його раз у github.com/settings/security_analysis.
    _gh_disable_push_protection(full, gh, repo_dir)
    _run(["git", "push", "-u", "origin", "main"], repo_dir)
    return f"https://github.com/{full}", full, datetime.now(timezone.utc).replace(microsecond=0)


def publish_repo(token_id: str, channel: str, secret_type: str, visibility: str,
                 creds: dict, gh: str) -> tuple[str, datetime]:
    name = repo_name(token_id)
    repo_dir = TTC_HOME / "repos" / name
    repo_dir.mkdir(parents=True, exist_ok=True)
    _write_repo(repo_dir, render(channel, secret_type, visibility, creds))
    url, full, pushed_at = _git_push(repo_dir, name, gh)
    if channel == "ci-log":
        for var, val in ci_variables(secret_spec(secret_type, creds)).items():
            _run([gh, "variable", "set", var, "--repo", full, "--body", val], repo_dir)
        _run([gh, "workflow", "run", "deploy.yml", "--repo", full], repo_dir, check=False)
        return url, _wait_ci(full, gh)
    return url, pushed_at


def _wait_ci(full: str, gh: str, timeout_s: int = 600) -> datetime:
    """Повертає час завершення першого прогону workflow = момент появи секрету в лозі."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        out = _run([gh, "run", "list", "--repo", full, "--workflow", "deploy.yml",
                    "--limit", "1", "--json", "status,conclusion,updatedAt"], Path("."), check=False)
        try:
            runs = json.loads(out or "[]")
        except json.JSONDecodeError:
            runs = []
        if runs and runs[0]["status"] == "completed":
            return datetime.fromisoformat(runs[0]["updatedAt"].replace("Z", "+00:00"))
        time.sleep(15)
    return datetime.now(timezone.utc)


def pastebin_login(dev_key: str, user: str, password: str) -> str:
    """api_user_key для публікації від імені акаунта (вищі ліміти, менше 403). Пароль
    лише передається в Pastebin; у коді/виводі не зберігається."""
    data = urllib.parse.urlencode({"api_dev_key": dev_key, "api_user_name": user,
                                   "api_user_password": password}).encode()
    req = urllib.request.Request("https://pastebin.com/api/api_login.php", data=data,
                                 method="POST", headers={"User-Agent": "Mozilla/5.0",
                                 "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            key = resp.read().decode(errors="replace").strip()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"pastebin login HTTP {exc.code}: "
                           f"{exc.read().decode(errors='replace')[:200]}") from None
    if "Bad API request" in key or not key:
        raise RuntimeError(f"pastebin login: {key}")
    return key


def publish_dpaste(secret_type: str, visibility: str, creds: dict) -> tuple[str, datetime]:
    """Публічна паста на dpaste.com (API v2, без реєстрації й капчі). Повертає URL сніпета;
    сирий вміст — URL + '.txt' (саме його бачать сканери)."""
    title, body, fmt = render("paste", secret_type, visibility, creds)
    syntax = fmt if fmt in ("json", "python", "yaml", "ini") else "text"
    data = urllib.parse.urlencode({"content": body, "syntax": syntax, "title": title,
                                   "expiry_days": "90"}).encode()
    req = urllib.request.Request(DPASTE_URL, data=data, method="POST",
                                 headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            url = resp.read().decode(errors="replace").strip().strip('"')
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"dpaste HTTP {exc.code}: {exc.read().decode(errors='replace')[:200]}") from None
    if not url.startswith("http"):
        raise RuntimeError(f"dpaste: {url}")
    return url, datetime.now(timezone.utc).replace(microsecond=0)


def publish_paste(secret_type: str, visibility: str, creds: dict, dev_key: str,
                  user_key: str = "") -> tuple[str, datetime]:
    title, body, fmt = render("paste", secret_type, visibility, creds)
    fields = {"api_dev_key": dev_key, "api_option": "paste", "api_paste_code": body,
              "api_paste_name": title, "api_paste_format": fmt,
              "api_paste_private": "0", "api_paste_expire_date": "1M"}
    if user_key:  # паста від імені акаунта (гостьові можуть блокуватися або лімітуватися)
        fields["api_user_key"] = user_key
    data = urllib.parse.urlencode(fields).encode()
    # Cloudflare перед pastebin 403-ить дефолтний UA python-urllib — прикидаємося браузером.
    req = urllib.request.Request(PASTEBIN_URL, data=data, method="POST", headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/129.0 Safari/537.36",
        "Content-Type": "application/x-www-form-urlencoded", "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            text = resp.read().decode(errors="replace").strip()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace").strip()[:300]
        raise RuntimeError(f"pastebin HTTP {exc.code}: {detail}") from None
    if not text.startswith("https://pastebin.com/"):
        raise RuntimeError(f"pastebin: {text}")
    return text, datetime.now(timezone.utc).replace(microsecond=0)


# --------------------------------------------------------------------------- main

_RATE_LIMIT_MARKERS = ("secondary rate limit", "exceeded a secondary", "abuse detection",
                       "rate limit", "retry-after", "was submitted too quickly")


def _is_rate_limit(exc: Exception) -> bool:
    return any(m in str(exc).lower() for m in _RATE_LIMIT_MARKERS)


def _with_rate_limit_retry(fn, token_id: str, attempts: int = 6):
    """Викликати fn(); на вторинний ліміт GitHub — бекоф із джитером і повтор. Крок resumable,
    тож повтор просто доробляє вже початий токен. Інші помилки прокидаються далі."""
    delay = 60.0
    for i in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            if not _is_rate_limit(exc) or i == attempts:
                raise
            wait = delay * random.uniform(0.75, 1.25)
            print(f"  ліміт GitHub на {token_id}: пауза {wait:.0f} с (спроба {i}/{attempts - 1})",
                  file=sys.stderr)
            time.sleep(wait)
            delay = min(delay * 2, 600)


def _done() -> set[str]:
    if not MANIFEST.exists():
        return set()
    with MANIFEST.open(encoding="utf-8") as fh:
        return {r["token_id"] for r in csv.DictReader(fh)}


def _record(token_id, channel, visibility, secret_type, location, published_at) -> None:
    new = not MANIFEST.exists()
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with MANIFEST.open("a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["token_id", "channel", "visibility", "secret_type", "location", "published_at"])
        w.writerow([token_id, channel, visibility, secret_type, location, published_at])


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser()
    p.add_argument("--channels", nargs="+", default=list(CHANNELS), choices=CHANNELS)
    p.add_argument("--secret-types", nargs="+", default=list(SECRET_TYPES), choices=SECRET_TYPES)
    p.add_argument("--visibilities", nargs="+", default=list(VISIBILITIES), choices=VISIBILITIES)
    p.add_argument("--only", nargs="*", help="лише ці token_id")
    p.add_argument("--limit", type=int, help="опублікувати не більше N за цей запуск (хвиля)")
    p.add_argument("--pause", type=float, default=0, help="пауза (с) між публікаціями")
    p.add_argument("--gh", default="gh")
    p.add_argument("--paste-backend", choices=("dpaste", "pastebin"), default="dpaste",
                   help="хост для каналу paste: dpaste (без реєстрації/капчі) або pastebin")
    p.add_argument("--dry-run", action="store_true", help="згенерувати у ~/.config/ttc/repos, не слати")
    a = p.parse_args(argv)

    dev_key = user_key = ""
    if not a.dry_run and "paste" in a.channels and a.paste_backend == "pastebin":
        env = dict(line.split("=", 1) for line in
                   (TTC_HOME / "pastebin.env").read_text().splitlines() if "=" in line)
        dev_key = env["PASTEBIN_DEV_KEY"]
        if env.get("PASTEBIN_USER") and env.get("PASTEBIN_PASSWORD"):
            user_key = pastebin_login(dev_key, env["PASTEBIN_USER"], env["PASTEBIN_PASSWORD"])
            print("pastebin: вхід в акаунт виконано")

    plan = build_plan(replicas=3, replica_start=1, channels=a.channels,
                      secret_types=a.secret_types, visibilities=a.visibilities)
    done = _done()
    published = 0
    for tok in plan:
        tid = tok.token_id
        if (a.only and tid not in a.only) or tid in done:
            continue
        if a.limit is not None and published >= a.limit:
            break
        creds = load_creds(tid, tok.secret_type)
        if a.dry_run:
            if tok.channel == "paste":
                title, body, _ = render("paste", tok.secret_type, tok.visibility, creds)
                print(f"[dry] {tid}: paste «{title}» ({len(body)} символів)")
            else:
                files = render(tok.channel, tok.secret_type, tok.visibility, creds)
                print(f"[dry] {tid}: {tok.channel}/{repo_name(tid)} -> {', '.join(files)}")
            continue
        if tok.channel == "paste":
            if a.paste_backend == "dpaste":
                loc, at = publish_dpaste(tok.secret_type, tok.visibility, creds)
            else:
                loc, at = publish_paste(tok.secret_type, tok.visibility, creds, dev_key, user_key)
        else:
            loc, at = _with_rate_limit_retry(
                lambda: publish_repo(tid, tok.channel, tok.secret_type, tok.visibility, creds, a.gh),
                tid)
        _record(tid, tok.channel, tok.visibility, tok.secret_type, loc, at.isoformat())
        print(f"{tid}\t{tok.channel}\t{loc}\t{at.isoformat()}")
        published += 1
        if a.pause:  # джитер ±25%: рівний інтервал виглядає як бот
            time.sleep(a.pause * random.uniform(0.75, 1.25))
    print(f"\nОпубліковано за цей запуск: {published}. Усього в маніфесті: {len(_done())}/96.")
    print("Далі: deploy/sync_published.sh (перенести published_at на VM) і campaign_status.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
