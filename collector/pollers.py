"""Опитувач хмарних журналів: CloudTrail (усі регіони) і GCP Cloud Audit Logs -> TtcStore.

Запуск на VM (systemd `ttc-poller`):
    python -m collector.pollers

Кожен прохід бере вікно [now - LOOKBACK, now]: CloudTrail доставляє події із затримкою
до ~15 хв, тож вікна перекриваються, а дублікати відкидає таблиця `seen` (EventId/insertId).
Кожен сирий запис спершу пишеться в raw-журнал (первинне джерело), потім розбирається.
"""
from __future__ import annotations

import csv
import json
import logging
import os
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable

from .cloud_events import (PG_CSV_COLUMNS, parse_cloudtrail_event, parse_gcp_audit_entry,
                           parse_pg_log_row)
from .store import TtcStore

log = logging.getLogger("ttc.poller")
LOOKBACK = timedelta(minutes=30)
# ec2:DescribeRegions може бути недоступним (неактивований акаунт) — тоді цей список
AWS_DEFAULT_REGIONS = (
    "us-east-1 us-east-2 us-west-1 us-west-2 ca-central-1 sa-east-1 eu-central-1 eu-west-1 "
    "eu-west-2 eu-west-3 eu-north-1 ap-south-1 ap-northeast-1 ap-northeast-2 ap-northeast-3 "
    "ap-southeast-1 ap-southeast-2").split()


def load_map(path: Path, key_col: str, value_col: str = "token_id") -> dict[str, str]:
    with open(path, encoding="utf-8") as fh:
        return {r[key_col]: r[value_col] for r in csv.DictReader(fh)}


class Poller:
    def __init__(self, store: TtcStore, raw_log: Path | str | None = None):
        self.store = store
        self.raw_log = raw_log
        self._lock = threading.Lock()
        self._db = sqlite3.connect(store.db_path, check_same_thread=False)
        self._db.execute("CREATE TABLE IF NOT EXISTS seen (source TEXT, id TEXT, "
                         "PRIMARY KEY (source, id))")
        self._db.commit()

    def _is_seen(self, source: str, item_id: str) -> bool:
        return self._db.execute("SELECT 1 FROM seen WHERE source = ? AND id = ?",
                                (source, item_id)).fetchone() is not None

    def _new(self, source: str, item_id: str) -> bool:
        cur = self._db.execute("INSERT OR IGNORE INTO seen VALUES (?, ?)", (source, item_id))
        self._db.commit()
        return cur.rowcount == 1

    def _raw(self, source: str, payload: dict) -> None:
        if self.raw_log is None:
            return
        line = json.dumps({"received_at": datetime.now(timezone.utc).isoformat(),
                           "source": source, "payload": payload},
                          ensure_ascii=False, default=str)
        with self._lock, open(self.raw_log, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def ingest(self, source: str, items: Iterable[dict], id_of: Callable[[dict], str],
               parse: Callable[[dict], object]) -> int:
        n = 0
        for item in items:
            item_id = id_of(item)
            if self._is_seen(source, item_id):
                continue
            ev = parse(item)
            if ev is not None and not self.store.known_token(ev.token_id):
                # не позначаємо як бачене: токен можуть зареєструвати пізніше, а запис
                # ще лишатиметься у вікні LOOKBACK наступних проходів
                log.warning("%s: event for unregistered token %s", source, ev.token_id)
                continue
            self._new(source, item_id)
            if ev is None:
                continue
            self._raw(source, item)
            self.store.record_event(ev)
            n += 1
        return n


# --------------------------------------------------------------------------- джерела

def cloudtrail_events(session, start: datetime, end: datetime) -> Iterable[dict]:
    try:
        regions = [r["RegionName"] for r in
                   session.client("ec2", region_name="us-east-1").describe_regions()["Regions"]]
    except Exception:  # noqa: BLE001 — неактивований акаунт: ec2 OptInRequired
        regions = list(AWS_DEFAULT_REGIONS)
    for region in regions:
        ct = session.client("cloudtrail", region_name=region)
        try:
            for page in ct.get_paginator("lookup_events").paginate(StartTime=start, EndTime=end):
                yield from page.get("Events", [])
        except Exception as exc:  # noqa: BLE001 — один регіон не має зупиняти решту
            log.warning("cloudtrail %s: %s", region, exc)


def gcp_entries(authed_session, project: str, start: datetime) -> Iterable[dict]:
    flt = (f'timestamp >= "{start.isoformat()}" AND logName:"cloudaudit.googleapis.com" AND '
           '(protoPayload.authenticationInfo.serviceAccountKeyName:* OR '
           'protoPayload.methodName:"DisableServiceAccountKey")')
    body = {"resourceNames": [f"projects/{project}"], "filter": flt,
            "orderBy": "timestamp asc", "pageSize": 1000}
    while True:
        r = authed_session.post("https://logging.googleapis.com/v2/entries:list", json=body,
                                timeout=60)
        r.raise_for_status()
        data = r.json()
        yield from data.get("entries", [])
        if not data.get("nextPageToken"):
            return
        body["pageToken"] = data["nextPageToken"]


def pg_log_rows(log_dir: Path) -> Iterable[dict]:
    """Рядки csvlog Postgres-пастки (файли postgresql-*.csv у змонтованому каталозі)."""
    for path in sorted(Path(log_dir).glob("*.csv")):
        with open(path, newline="", encoding="utf-8", errors="replace") as fh:
            for rec in csv.reader(fh):
                yield dict(zip(PG_CSV_COLUMNS, rec))


# --------------------------------------------------------------------------- main

def main() -> None:  # pragma: no cover — інтеграційний цикл, перевіряється на VM
    import boto3
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2 import service_account

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = Path(os.environ.get("TTC_CLOUD_DIR", "/etc/ttc/cloud"))
    poller = Poller(TtcStore(os.environ.get("TTC_DB", "data/ttc.db")),
                    os.environ.get("TTC_POLL_RAW_LOG") or None)
    aws_keys = load_map(cfg / "aws-users.csv", "access_key_id")
    aws_users = load_map(cfg / "aws-users.csv", "user_name")
    gcp_keys = load_map(cfg / "gcp-accounts.csv", "key_id")
    project = (cfg / "gcp-project").read_text().strip()
    reader = service_account.Credentials.from_service_account_file(
        str(cfg / "gcp-reader.json"), scopes=["https://www.googleapis.com/auth/logging.read"])
    own = frozenset({reader.service_account_email})
    gcp = AuthorizedSession(reader)
    aws = boto3.Session()  # AWS_ACCESS_KEY_ID/SECRET з EnvironmentFile (cloudtrail-reader)
    pg_users = load_map(cfg / "db-creds.csv", "user")
    pg_dir = Path(os.environ.get("TTC_PG_LOG_DIR", "/var/lib/ttc/pglog"))
    interval = int(os.environ.get("TTC_POLL_SECONDS", "60"))

    while True:
        now = datetime.now(timezone.utc)
        start = now - LOOKBACK
        for name, fn in (
            ("cloudtrail", lambda: poller.ingest(
                "cloudtrail", cloudtrail_events(aws, start, now), lambda e: e["EventId"],
                lambda e: parse_cloudtrail_event(e, aws_keys, aws_users))),
            ("gcp-audit", lambda: poller.ingest(
                "gcp-audit", gcp_entries(gcp, project, start), lambda e: e["insertId"],
                lambda e: parse_gcp_audit_entry(e, gcp_keys, own))),
            ("pg-trap", lambda: poller.ingest(
                "pg-trap", pg_log_rows(pg_dir),
                lambda r: f"{r.get('session_id')}:{r.get('session_line_num')}",
                lambda r: parse_pg_log_row(r, pg_users))),
        ):
            try:
                n = fn()
                if n:
                    log.info("%s: +%d events", name, n)
            except Exception:  # noqa: BLE001 — збій одного джерела не зупиняє інше
                log.exception("%s poll failed", name)
        time.sleep(interval)


if __name__ == "__main__":
    main()
