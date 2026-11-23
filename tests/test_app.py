# diploma/experiment/tests/test_app.py
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from collector.app import create_app
from collector.model import Honeytoken
from collector.store import TtcStore


def test_hit_endpoint_records_ttc(tmp_path):
    store = TtcStore(tmp_path / "ttc.db")
    store.register(Honeytoken("t1", "aws", "github", "obvious",
                              datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)))
    app = create_app(store)
    client = TestClient(app)

    resp = client.post("/hit", json={
        "token_id": "t1",
        "used_at": "2026-07-01T12:04:00+00:00",
        "source_ip": "203.0.113.9",
    })
    assert resp.status_code == 200
    rows = store.export_rows()
    assert rows[0]["ttc_seconds"] == 240.0
    assert rows[0]["censored"] == 0


def test_hit_unknown_token_returns_404(tmp_path):
    store = TtcStore(tmp_path / "ttc.db")
    client = TestClient(create_app(store))
    resp = client.post("/hit", json={
        "token_id": "nope", "used_at": "2026-07-01T12:00:00+00:00", "source_ip": "x",
    })
    assert resp.status_code == 404
