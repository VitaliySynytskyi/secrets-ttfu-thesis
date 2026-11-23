# diploma/experiment/tests/test_set_published.py
from datetime import datetime, timezone

import pytest

from collector.model import Honeytoken
from collector.store import TtcStore
from deploy.set_published import main


def test_set_published_updates_only_that_token(tmp_path):
    db = tmp_path / "ttc.db"
    s = TtcStore(db)
    t0 = datetime(2026, 9, 6, tzinfo=timezone.utc)
    s.register(Honeytoken("a", "aws", "github", "obvious", t0))
    s.register(Honeytoken("b", "api", "dotenv", "buried", t0))
    assert main(["--db", str(db), "a", "2026-10-07T14:30:00+00:00"]) == 0
    rows = {r["token_id"]: r for r in TtcStore(db).export_rows(
        now=datetime(2026, 10, 7, 15, 30, tzinfo=timezone.utc))}
    assert rows["a"]["ttc_seconds"] == 3600.0
    assert rows["b"]["ttc_seconds"] > 3600.0


def test_set_published_rejects_unknown_token_and_naive_time(tmp_path):
    db = tmp_path / "ttc.db"
    TtcStore(db).register(Honeytoken("a", "aws", "github", "obvious",
                                     datetime(2026, 9, 6, tzinfo=timezone.utc)))
    assert main(["--db", str(db), "zz", "2026-10-07T14:30:00+00:00"]) == 1
    with pytest.raises(SystemExit):
        main(["--db", str(db), "a", "2026-10-07T14:30:00"])


def test_batch_from_csv_is_all_or_nothing(tmp_path):
    from datetime import datetime, timezone
    from collector.model import Honeytoken
    from collector.store import TtcStore
    from deploy.set_published import main
    db = tmp_path / "t.db"
    s = TtcStore(db)
    t0 = datetime(2026, 10, 16, tzinfo=timezone.utc)
    for tid in ("github-aws-obvious-1", "paste-db-buried-2"):
        s.register(Honeytoken(tid, tid.split("-")[1], tid.split("-")[0], "obvious", t0))
    bad = tmp_path / "bad.csv"
    bad.write_text("token_id,published_at\ngithub-aws-obvious-1,2026-10-17T10:00:00+00:00\n"
                   "nope-1,2026-10-17T10:00:00+00:00\n", encoding="utf-8")
    assert main(["--db", str(db), "--from-csv", str(bad)]) == 1
    assert all(r["ttc_seconds"] > 0 for r in TtcStore(db).export_rows(
        now=datetime(2026, 10, 16, 1, tzinfo=timezone.utc)))
    good = tmp_path / "good.csv"
    good.write_text("token_id,location,published_at\n"
                    "github-aws-obvious-1,x,2026-10-17T10:00:00+00:00\n"
                    "paste-db-buried-2,y,2026-10-17T11:30:00+00:00\n", encoding="utf-8")
    assert main(["--db", str(db), "--from-csv", str(good)]) == 0
    pub = dict(TtcStore(db)._conn.execute("SELECT token_id, published_at FROM tokens"))
    assert pub["paste-db-buried-2"].startswith("2026-10-17T11:30")
