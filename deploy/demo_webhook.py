"""Наскрізна локальна демонстрація «як ми ловимо використання токена».

Піднімає справжній колектор (uvicorn) на localhost, реєструє 3 токени і надсилає йому
HTTP-запити у форматі, який надсилає canarytokens.org (TokenAlertDetails /
TokenExposedDetails з thinkst/canarytokens). Нічого не публікує назовні.

    .venv/Scripts/python.exe deploy/demo_webhook.py --out data/demo
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from collector.app import create_app  # noqa: E402
from collector.model import Honeytoken  # noqa: E402
from collector.store import TtcStore  # noqa: E402

FMT = "%Y-%m-%d %H:%M:%S (UTC)"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/demo")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    db = out / "demo.db"
    db.unlink(missing_ok=True)

    t0 = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)
    store = TtcStore(db)
    for tid, st, ch, vis in [("github-aws-obvious-0", "aws", "github", "obvious"),
                             ("paste-db-buried-0", "db", "paste", "buried"),
                             ("dotenv-api-obvious-0", "api", "dotenv", "obvious")]:
        store.register(Honeytoken(tid, st, ch, vis, t0))

    server = uvicorn.Server(uvicorn.Config(create_app(store), host="127.0.0.1",
                                           port=args.port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)

    base = f"http://127.0.0.1:{args.port}/canarytokens"
    manage = "https://canarytokens.org/nest/manage/demo"
    requests = [
        ("AWS-ключ у GitHub: платформа знайшла ключ (exposed) через 2 хв",
         {"token_type": "aws_keys", "token": "demo1", "memo": "token_id=github-aws-obvious-0",
          "key_id": "AKIAEXAMPLEDEMO", "public_location": "https://github.com/demo/repo/blob/main/.env",
          "exposed_time": (t0 + timedelta(minutes=2)).strftime(FMT), "manage_url": manage}),
        ("AWS-ключ у GitHub: сканер викликав AWS API (use) через 4 хв",
         {"channel": "AWS API Key", "token_type": "aws_keys", "src_ip": "198.51.100.23", "token": "demo1",
          "time": (t0 + timedelta(minutes=4)).strftime(FMT), "memo": "token_id=github-aws-obvious-0",
          "manage_url": manage, "additional_data": {"aws_key_log_data": {"eventName": ["GetCallerIdentity"]},
                                                    "useragent": "Boto3/1.34 Python/3.11"}}),
        ("Рядок підключення БД на paste-сервісі: DNS-запит до хоста-приманки через 9 год",
         {"channel": "DNS", "token_type": "dns", "src_ip": "192.0.2.53", "token": "demo2",
          "time": (t0 + timedelta(hours=9)).strftime(FMT), "memo": "token_id=paste-db-buried-0",
          "manage_url": manage, "additional_data": None}),
        ("Невідомий токен (не з нашого реєстру) — має бути відхилений",
         {"channel": "HTTP", "token_type": "web", "src_ip": "203.0.113.1", "token": "x",
          "time": t0.strftime(FMT), "memo": "token_id=someone-else", "manage_url": manage}),
    ]
    log = []
    with httpx.Client(timeout=5) as c:
        for title, payload in requests:
            r = c.post(base, json=payload)
            log.append({"step": title, "http_status": r.status_code, "response": r.json()})
            print(f"[{r.status_code}] {title}\n      -> {r.json()}")
    server.should_exit = True

    now = t0 + timedelta(days=3)
    rows = store.export_rows(now=now)
    store.export_csv(out / "demo-ttc.csv", now=now)
    events = store._conn.execute("SELECT token_id, kind, at, source_ip FROM events ORDER BY at").fetchall()
    print("\nТаблиця events (сире сховище подій):")
    for e in events:
        print("  ", e)
    print("\nЕкспорт для аналізу (станом на t0 + 3 доби):")
    for r in rows:
        print("  ", r)
    (out / "demo-log.json").write_text(json.dumps({"requests": log, "events": events, "export": rows},
                                                  ensure_ascii=False, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
