# diploma/experiment/tests/test_canarytokens.py
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from collector.app import create_app
from collector.canarytokens import parse_canarytokens_payload
from collector.model import Honeytoken
from collector.store import TtcStore

PUBLISHED = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)


def _alert(memo="token_id=github-aws-obvious-0", time="2026-10-01 12:04:00 (UTC)",
           src_ip="203.0.113.9", **extra):
    # Форма TokenAlertDetails з thinkst/canarytokens (canarytokens/models/common.py).
    return {"channel": "HTTP", "token_type": "aws_keys", "src_ip": src_ip, "token": "abc123",
            "time": time, "memo": memo, "manage_url": "https://canarytokens.org/nest/manage/x",
            "additional_data": extra.get("additional_data"), "public_domain": "canarytokens.org"}


def test_parse_alert_extracts_token_id_time_ip():
    ev = parse_canarytokens_payload(_alert())
    assert ev.kind == "use"
    assert ev.token_id == "github-aws-obvious-0"
    assert ev.at == datetime(2026, 10, 1, 12, 4, 0, tzinfo=timezone.utc)
    assert ev.source_ip == "203.0.113.9"


def test_parse_memo_that_is_just_the_id():
    assert parse_canarytokens_payload(_alert(memo="paste-db-buried-2")).token_id == "paste-db-buried-2"


def test_parse_safety_net_alert():
    payload = _alert(src_ip=None, additional_data={
        "aws_key_log_data": {"safety_net": ["True"], "service_used": ["sts"]}})
    ev = parse_canarytokens_payload(payload)
    assert ev.kind == "safety_net"
    assert ev.source_ip == ""


def test_parse_exposed_notification():
    payload = {"token_type": "aws_keys", "token": "abc123", "memo": "token_id=github-aws-obvious-0",
               "key_id": "AKIAEXAMPLE", "public_location": "https://github.com/x/y/blob/main/.env",
               "exposed_time": "2026-10-01 12:02:00 (UTC)",
               "manage_url": "https://canarytokens.org/nest/manage/x"}
    ev = parse_canarytokens_payload(payload)
    assert ev.kind == "exposed"
    assert ev.at == datetime(2026, 10, 1, 12, 2, 0, tzinfo=timezone.utc)
    assert ev.public_location.endswith(".env")


def test_aws_internal_quarantine_is_exposure_not_use():
    # Реальний payload кампанії (2026-10-06): AWS сам навішує карантинну політику на ключ,
    # про який дізнався від GitHub secret scanning. Це захисна реакція, а не атакувальник.
    payload = _alert(src_ip="AWS Internal", additional_data={
        "useragent": "AWS Internal",
        "aws_key_log_data": {"eventName": ["AttachUserPolicy"], "accountId": ["1"]}})
    ev = parse_canarytokens_payload(payload)
    assert ev.kind == "exposed"
    assert ev.source_ip == ""
    assert ev.public_location == "aws-quarantine:AttachUserPolicy"


def test_parse_rejects_payload_without_time():
    with pytest.raises(ValueError):
        parse_canarytokens_payload({"memo": "token_id=x"})


def _client(tmp_path):
    store = TtcStore(tmp_path / "ttc.db")
    store.register(Honeytoken("github-aws-obvious-0", "aws", "github", "obvious", PUBLISHED))
    return store, TestClient(create_app(store))


def test_canarytokens_endpoint_records_use_as_ttfu(tmp_path):
    store, client = _client(tmp_path)
    resp = client.post("/canarytokens", json=_alert())
    assert resp.status_code == 200
    assert resp.json()["kind"] == "use"
    row = store.export_rows()[0]
    assert row["ttc_seconds"] == 240.0
    assert row["censored"] == 0
    assert row["time_precise"] == 1


def test_exposed_does_not_count_as_attacker_use(tmp_path):
    store, client = _client(tmp_path)
    client.post("/canarytokens", json={
        "token_type": "aws_keys", "token": "abc", "memo": "token_id=github-aws-obvious-0",
        "key_id": "AKIA", "exposed_time": "2026-10-01 12:02:00 (UTC)",
        "manage_url": "https://canarytokens.org/nest/manage/x"})
    row = store.export_rows(now=datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc))[0]
    assert row["censored"] == 1                 # зловмисник ще не використав
    assert row["exposed_seconds"] == 120.0      # а платформа знайшла ключ за 2 хв


def test_safety_net_only_gives_imprecise_upper_bound(tmp_path):
    store, client = _client(tmp_path)
    client.post("/canarytokens", json=_alert(src_ip=None, time="2026-10-01 15:00:00 (UTC)", additional_data={
        "aws_key_log_data": {"safety_net": ["True"], "service_used": ["sts"]}}))
    row = store.export_rows()[0]
    assert row["censored"] == 0
    assert row["ttc_seconds"] == 3 * 3600.0
    assert row["time_precise"] == 0


def test_canarytokens_endpoint_unknown_token_404(tmp_path):
    _, client = _client(tmp_path)
    assert client.post("/canarytokens", json=_alert(memo="token_id=nope")).status_code == 404


def test_canarytokens_endpoint_malformed_422(tmp_path):
    _, client = _client(tmp_path)
    assert client.post("/canarytokens", json={"hello": "world"}).status_code == 422
