"""Згенерувати облікові дані для токенів `db` і `api` основної кампанії (репліки 1-3 + calib).

  ~/.config/ttc/db/creds.csv   token_id,user,password   -> ролі Postgres-пастки на VM
  ~/.config/ttc/api/keys.csv   token_id,api_key         -> ключі API-пастки на VM

Повторний запуск нічого не перегенеровує (опубліковані значення мають лишатися сталими).
    python deploy/cloud/gen_local_creds.py
"""
from __future__ import annotations

import csv
import os
import secrets
import string
import sys
from pathlib import Path

TTC_HOME = Path(os.environ.get("TTC_HOME", Path.home() / ".config" / "ttc"))
CHANNELS = ("github", "ci-log", "paste", "dotenv")
VISIBILITIES = ("obvious", "buried")

# нейтральні імена ролей: схожі на звичайних користувачів застосунків.
# Публічна версія: імена-приклади (у реальній кампанії використано інший набір).
DB_USERS = [f"app_user_{i:02d}" for i in range(1, 26)]


def token_ids(secret_type: str) -> list[str]:
    ids = [f"{ch}-{secret_type}-{vis}-{r}"
           for ch in CHANNELS for vis in VISIBILITIES for r in (1, 2, 3)]
    return ids + [f"calib-{secret_type}-0"]


def _password(n: int = 24) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(n))


def _write_once(path: Path, header: list[str], rows: list[list[str]]) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    path.chmod(0o600)
    return True


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    db_ids = token_ids("db")
    assert len(DB_USERS) >= len(db_ids)
    db = _write_once(TTC_HOME / "db" / "creds.csv", ["token_id", "user", "password"],
                     [[t, u, _password()] for t, u in zip(db_ids, DB_USERS)])
    api = _write_once(TTC_HOME / "api" / "keys.csv", ["token_id", "api_key"],
                      [[t, "sk_live_" + secrets.token_hex(20)] for t in token_ids("api")])
    print(f"db: {'створено' if db else 'вже існує'}; api: {'створено' if api else 'вже існує'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
