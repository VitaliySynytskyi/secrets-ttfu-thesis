# diploma/experiment/tests/test_rebuild_from_raw.py
import json
from datetime import datetime, timezone

from collector.model import Hit, Honeytoken
from collector.store import TtcStore
from deploy.rebuild_from_raw import rebuild

PUB = datetime(2026, 10, 6, 19, 3, 15, tzinfo=timezone.utc)


def _line(payload):
    return json.dumps({"received_at": "2026-10-06T19:06:10+00:00", "payload": payload})


def test_rebuild_reclassifies_aws_quarantine_and_keeps_real_use(tmp_path):
    store = TtcStore(tmp_path / "ttc.db")
    store.register(Honeytoken("a", "aws", "github", "obvious", PUB))
    # стара (хибна) класифікація карантину як використання
    store.record_hit(Hit("a", datetime(2026, 10, 6, 19, 6, 10, tzinfo=timezone.utc), "AWS Internal"))
    raw = tmp_path / "raw.jsonl"
    raw.write_text("\n".join([
        _line({"token": "a+test+token", "time": "2026-10-06 18:24:03 (UTC)", "memo": "x"}),
        _line({"time": "2026-10-06 19:06:10 (UTC)", "memo": "token_id=a", "src_ip": "AWS Internal",
               "additional_data": {"useragent": "AWS Internal",
                                   "aws_key_log_data": {"eventName": ["AttachUserPolicy"]}}}),
        _line({"time": "2026-10-06 20:03:15 (UTC)", "memo": "token_id=a", "src_ip": "198.51.100.7"}),
        _line({"time": "2026-10-06 18:29:25 (UTC)", "memo": "token_id=calib-aws-0", "src_ip": "x"}),
        _line({"memo": "token_id=a"}),
    ]) + "\n", encoding="utf-8")

    stats = rebuild(store, raw)

    assert stats == {"webhook-test": 1, "exposed": 1, "use": 1, "unknown-token": 1, "unparseable": 1}
    row = store.export_rows(now=datetime(2026, 10, 7, tzinfo=timezone.utc))[0]
    assert row["ttc_seconds"] == 3600.0 and row["censored"] == 0
    assert row["exposed_seconds"] == 175.0


def test_rebuild_is_idempotent(tmp_path):
    store = TtcStore(tmp_path / "ttc.db")
    store.register(Honeytoken("a", "aws", "github", "obvious", PUB))
    raw = tmp_path / "raw.jsonl"
    raw.write_text(_line({"time": "2026-10-06 20:03:15 (UTC)", "memo": "token_id=a",
                          "src_ip": "198.51.100.7"}) + "\n", encoding="utf-8")
    rebuild(store, raw)
    rebuild(store, raw)
    assert store._conn.execute("SELECT COUNT(*) FROM hits").fetchone()[0] == 1
