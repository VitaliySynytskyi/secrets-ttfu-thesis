# diploma/experiment/tests/test_app_production.py
"""Продакшн-режим колектора: секретний шлях webhook, сирий журнал подій, healthcheck."""
import json
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from collector.app import create_app
from collector.main import build_app
from collector.model import Honeytoken
from collector.store import TtcStore

PUBLISHED = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)
ALERT = {"channel": "HTTP", "token_type": "aws_keys", "src_ip": "203.0.113.9", "token": "abc",
         "time": "2026-10-01 12:04:00 (UTC)", "memo": "token_id=t1",
         "manage_url": "https://canarytokens.org/nest/manage/x", "additional_data": None}


def _store(tmp_path):
    store = TtcStore(tmp_path / "ttc.db")
    store.register(Honeytoken("t1", "aws", "github", "obvious", PUBLISHED))
    return store


def test_secret_path_accepts_and_plain_path_is_closed(tmp_path):
    store = _store(tmp_path)
    client = TestClient(create_app(store, webhook_secret="s3cr3t"))
    assert client.post("/canarytokens", json=ALERT).status_code == 404
    assert client.post("/canarytokens/wrong", json=ALERT).status_code == 404
    assert client.post("/hit", json={"token_id": "t1", "used_at": "2026-10-01T12:04:00+00:00",
                                     "source_ip": "x"}).status_code == 404
    resp = client.post("/canarytokens/s3cr3t", json=ALERT)
    assert resp.status_code == 200
    assert store.export_rows()[0]["ttc_seconds"] == 240.0


def test_raw_log_keeps_every_payload_even_unparseable(tmp_path):
    store = _store(tmp_path)
    raw = tmp_path / "raw.jsonl"
    client = TestClient(create_app(store, raw_log=raw))
    client.post("/canarytokens", json=ALERT)
    client.post("/canarytokens", json={"memo": "token_id=t1"})          # без часу -> 422
    client.post("/canarytokens", json={**ALERT, "memo": "token_id=zz"})  # невідомий -> 404
    lines = [json.loads(l) for l in raw.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 3
    assert lines[0]["payload"]["memo"] == "token_id=t1"
    assert "received_at" in lines[0]


def test_canarytokens_webhook_test_ping_is_acknowledged_not_recorded(tmp_path):
    # canarytokens.org перед створенням токена POST-ить такий payload і чекає 2xx.
    store = _store(tmp_path)
    client = TestClient(create_app(store, webhook_secret="s"))
    ping = {"channel": "HTTP", "token_type": "aws_keys", "src_ip": "127.0.0.1",
            "token": "a+test+token", "time": "2026-10-06 18:24:03 (UTC)",
            "memo": "Congrats! The newly saved webhook works",
            "manage_url": "http://example.com/test/url/for/webhook"}
    resp = client.post("/canarytokens/s", json=ping)
    assert resp.status_code == 200 and resp.json()["status"] == "webhook-test"
    assert store.export_rows()[0]["censored"] == 1


def test_healthz_reports_token_count(tmp_path):
    client = TestClient(create_app(_store(tmp_path)))
    assert client.get("/healthz").json() == {"status": "ok", "tokens": 1}


def test_build_app_reads_env(tmp_path, monkeypatch):
    _store(tmp_path)
    monkeypatch.setenv("TTC_DB", str(tmp_path / "ttc.db"))
    monkeypatch.setenv("TTC_WEBHOOK_SECRET", "abc")
    monkeypatch.setenv("TTC_RAW_LOG", str(tmp_path / "raw.jsonl"))
    client = TestClient(build_app())
    assert client.post("/canarytokens/abc", json=ALERT).status_code == 200
    assert (tmp_path / "raw.jsonl").exists()
