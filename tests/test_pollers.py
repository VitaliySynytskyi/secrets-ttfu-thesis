import json
from datetime import datetime, timezone

from collector.cloud_events import parse_cloudtrail_event
from collector.model import Honeytoken
from collector.pollers import Poller
from collector.store import TtcStore

KEYS = {"AKIA1": "github-aws-obvious-1"}


def _ev(event_id, key="AKIA1", t="2026-10-16T18:46:59Z"):
    return {"EventId": event_id, "CloudTrailEvent": json.dumps({
        "eventTime": t, "eventName": "GetCallerIdentity", "sourceIPAddress": "203.0.113.7",
        "userIdentity": {"accessKeyId": key}})}


def _poller(tmp_path):
    store = TtcStore(tmp_path / "ttc.db")
    store.register(Honeytoken("github-aws-obvious-1", "aws", "github", "obvious",
                              datetime(2026, 10, 16, 18, 0, tzinfo=timezone.utc)))
    return store, Poller(store, raw_log=tmp_path / "raw.jsonl")


def test_ingest_records_use_and_deduplicates_overlapping_windows(tmp_path):
    store, poller = _poller(tmp_path)
    parse = lambda e: parse_cloudtrail_event(e, KEYS, {})  # noqa: E731
    assert poller.ingest("cloudtrail", [_ev("a"), _ev("b", t="2026-10-16T18:50:00Z")],
                         lambda e: e["EventId"], parse) == 2
    # наступне вікно перекривається: "b" вже бачили
    assert poller.ingest("cloudtrail", [_ev("b")], lambda e: e["EventId"], parse) == 0
    row = next(r for r in store.export_rows() if r["token_id"] == "github-aws-obvious-1")
    assert row["censored"] == 0
    assert row["ttc_seconds"] == 46 * 60 + 59
    assert len((tmp_path / "raw.jsonl").read_text().splitlines()) == 2


def test_ingest_skips_foreign_keys_and_unregistered_tokens(tmp_path):
    store, poller = _poller(tmp_path)
    parse = lambda e: parse_cloudtrail_event(  # noqa: E731
        e, {"AKIA1": "github-aws-obvious-1", "AKIA2": "not-registered"}, {})
    n = poller.ingest("cloudtrail", [_ev("x", key="ASIAOWN"), _ev("y", key="AKIA2")],
                      lambda e: e["EventId"], parse)
    assert n == 0
    assert all(r["censored"] == 1 for r in store.export_rows())


def test_event_for_later_registered_token_is_not_lost(tmp_path):
    store, poller = _poller(tmp_path)
    keys = {"AKIA9": "calib-aws-0"}
    parse = lambda e: parse_cloudtrail_event(e, keys, {})  # noqa: E731
    assert poller.ingest("cloudtrail", [_ev("late", key="AKIA9")], lambda e: e["EventId"], parse) == 0
    store.register(Honeytoken("calib-aws-0", "aws", "calib", "obvious",
                              datetime(2026, 10, 16, 18, 0, tzinfo=timezone.utc)))
    assert poller.ingest("cloudtrail", [_ev("late", key="AKIA9")], lambda e: e["EventId"], parse) == 1
