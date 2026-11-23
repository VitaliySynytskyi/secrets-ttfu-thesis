# diploma/experiment/tests/test_store.py
from datetime import datetime, timezone
from collector.model import Honeytoken, Hit
from collector.store import TtcStore


def _utc(*a):
    return datetime(*a, tzinfo=timezone.utc)


def test_empty_store_exports_no_rows(tmp_path):
    assert TtcStore(tmp_path / "ttc.db").export_rows() == []


def test_register_and_record_hit_produces_ttc_row(tmp_path):
    store = TtcStore(tmp_path / "ttc.db")
    store.register(Honeytoken("t1", "aws", "github", "obvious", _utc(2026, 7, 1, 12, 0, 0)))
    store.record_hit(Hit("t1", _utc(2026, 7, 1, 12, 5, 0), "203.0.113.7"))

    rows = store.export_rows()
    assert len(rows) == 1
    row = rows[0]
    assert row["token_id"] == "t1"
    assert row["secret_type"] == "aws"
    assert row["channel"] == "github"
    assert row["ttc_seconds"] == 300.0
    assert row["censored"] == 0


def test_unhit_token_is_censored(tmp_path):
    store = TtcStore(tmp_path / "ttc.db")
    store.register(Honeytoken("t2", "db", "paste", "buried", _utc(2026, 7, 1, 0, 0, 0)))
    rows = store.export_rows(now=_utc(2026, 7, 2, 0, 0, 0))
    assert len(rows) == 1
    assert rows[0]["censored"] == 1
    assert rows[0]["ttc_seconds"] == 86400.0  # тривалість спостереження


def test_first_hit_wins(tmp_path):
    store = TtcStore(tmp_path / "ttc.db")
    store.register(Honeytoken("t3", "api", "ci-log", "obvious", _utc(2026, 7, 1, 0, 0, 0)))
    store.record_hit(Hit("t3", _utc(2026, 7, 1, 0, 10, 0), "a"))
    store.record_hit(Hit("t3", _utc(2026, 7, 1, 0, 30, 0), "b"))
    assert store.export_rows()[0]["ttc_seconds"] == 600.0


def test_export_csv_writes_header(tmp_path):
    store = TtcStore(tmp_path / "ttc.db")
    store.register(Honeytoken("t1", "aws", "github", "obvious", _utc(2026, 7, 1, 12, 0, 0)))
    store.record_hit(Hit("t1", _utc(2026, 7, 1, 12, 5, 0), "x"))
    out = tmp_path / "ttc.csv"
    store.export_csv(out)
    text = out.read_text(encoding="utf-8")
    assert "token_id,secret_type,channel,visibility,ttc_seconds,censored" in text.splitlines()[0]
