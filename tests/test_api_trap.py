from datetime import datetime, timezone

from fastapi.testclient import TestClient

from collector.app import create_app
from collector.model import Honeytoken
from collector.store import TtcStore

KEYS = {"sk_live_abc": "github-api-obvious-1"}


def _client(tmp_path):
    store = TtcStore(tmp_path / "ttc.db")
    store.register(Honeytoken("github-api-obvious-1", "api", "github", "obvious",
                              datetime(2026, 10, 16, 18, 0, tzinfo=timezone.utc)))
    app = create_app(store, webhook_secret="s", raw_log=tmp_path / "raw.jsonl", api_keys=KEYS)
    return store, TestClient(app)


def test_known_key_records_use_with_forwarded_ip(tmp_path):
    store, c = _client(tmp_path)
    r = c.get("/api-trap/v1/orders", headers={"Authorization": "Bearer sk_live_abc",
                                              "X-Forwarded-For": "203.0.113.5"})
    assert r.status_code == 403
    row = store.export_rows()[0]
    assert row["censored"] == 0
    assert "203.0.113.5" in (tmp_path / "raw.jsonl").read_text()


def test_x_api_key_and_query_param_accepted(tmp_path):
    store, c = _client(tmp_path)
    assert c.post("/api-trap/v1/x", headers={"X-API-Key": "sk_live_abc"}).status_code == 403
    assert c.get("/api-trap/v1/x?api_key=sk_live_abc").status_code == 403


def test_unknown_key_only_logged(tmp_path):
    store, c = _client(tmp_path)
    assert c.get("/api-trap/", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert store.export_rows()[0]["censored"] == 1
    assert (tmp_path / "raw.jsonl").read_text().count("api-trap") == 1


def test_trap_disabled_without_keys(tmp_path):
    app = create_app(TtcStore(tmp_path / "t.db"), webhook_secret="s")
    assert TestClient(app).get("/api-trap/v1").status_code == 404
