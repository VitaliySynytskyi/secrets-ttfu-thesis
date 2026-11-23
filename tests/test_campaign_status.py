from datetime import datetime, timezone

from collector.canarytokens import CanaryEvent
from collector.model import Honeytoken
from collector.store import TtcStore
from deploy.campaign_status import collect


def _store(tmp_path):
    s = TtcStore(tmp_path / "ttc.db")
    t0 = datetime(2026, 10, 17, 10, 0, tzinfo=timezone.utc)
    s.register(Honeytoken("github-aws-obvious-1", "aws", "github", "obvious", t0))
    s.register(Honeytoken("paste-db-buried-2", "db", "paste", "buried", t0))
    s.register(Honeytoken("calib-aws-0", "aws", "calib", "obvious", t0))   # не входить
    s.register(Honeytoken("github-aws-obvious-0", "aws", "github", "obvious", t0))  # пілот, не входить
    return s, t0


def test_counts_only_campaign_tokens_and_events(tmp_path):
    s, t0 = _store(tmp_path)
    s.record_event(CanaryEvent("use", "github-aws-obvious-1",
                               datetime(2026, 10, 17, 11, 0, tzinfo=timezone.utc), "1.2.3.4"))
    s.record_event(CanaryEvent("exposed", "github-aws-obvious-1",
                               datetime(2026, 10, 17, 10, 3, tzinfo=timezone.utc), "AWS Internal"))
    st = collect(str(tmp_path / "ttc.db"), None, None)
    assert st["tokens_registered"] == 2
    assert st["tokens_used"] == 1
    assert st["events"] == {"use": 1, "exposed": 1}
    assert st["used_by_channel"] == {"github": 1}


def test_flags_use_before_publish(tmp_path):
    s, t0 = _store(tmp_path)
    s.record_event(CanaryEvent("use", "paste-db-buried-2",
                               datetime(2026, 10, 17, 9, 0, tzinfo=timezone.utc), "9.9.9.9"))
    st = collect(str(tmp_path / "ttc.db"), None, None)
    assert [a[0] for a in st["anomalies_use_before_publish"]] == ["paste-db-buried-2"]


def test_manifest_coverage(tmp_path):
    s, t0 = _store(tmp_path)
    man = tmp_path / "pub.csv"
    man.write_text("token_id,published_at\ngithub-aws-obvious-1,2026-10-17T10:00:00+00:00\n",
                   encoding="utf-8")
    st = collect(str(tmp_path / "ttc.db"), str(man), None)
    assert st["published_in_manifest"] == 1
    assert st["missing_from_manifest"] == ["paste-db-buried-2"]
