# diploma/experiment/collector/main.py
"""Точка входу для uvicorn (продакшн-запуск на сервері):

    TTC_DB=data/ttc.db TTC_WEBHOOK_SECRET=<секрет> TTC_RAW_LOG=data/raw-events.jsonl \
        python -m uvicorn collector.main:build_app --factory --host 127.0.0.1 --port 8000
"""
from __future__ import annotations
import csv
import os

from fastapi import FastAPI

from .app import create_app
from .store import TtcStore


def _api_keys() -> dict[str, str] | None:
    """TTC_API_KEYS: csv token_id,api_key (з deploy/cloud/gen_local_creds.py)."""
    path = os.environ.get("TTC_API_KEYS")
    if not path or not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return {r["api_key"]: r["token_id"] for r in csv.DictReader(fh)}


def build_app() -> FastAPI:
    return create_app(
        TtcStore(os.environ.get("TTC_DB", "data/ttc.db")),
        webhook_secret=os.environ.get("TTC_WEBHOOK_SECRET") or None,
        raw_log=os.environ.get("TTC_RAW_LOG") or None,
        api_keys=_api_keys(),
    )
