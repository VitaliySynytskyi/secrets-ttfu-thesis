# diploma/experiment/tests/test_export.py
import csv
from datetime import datetime, timezone
from collector.model import Honeytoken, Hit
from collector.store import TtcStore
from deploy.export import main


def test_export_cli_writes_csv_with_fixed_window(tmp_path):
    db, out = tmp_path / "ttc.db", tmp_path / "ttc.csv"
    s = TtcStore(db)
    t0 = datetime(2026, 10, 1, tzinfo=timezone.utc)
    s.register(Honeytoken("a", "aws", "github", "obvious", t0))
    s.register(Honeytoken("b", "db", "paste", "buried", t0))
    s.record_hit(Hit("a", datetime(2026, 10, 1, 0, 5, tzinfo=timezone.utc), "x"))
    assert main(["--db", str(db), "--out", str(out), "--now", "2026-10-31T00:00:00+00:00"]) == 0
    rows = {r["token_id"]: r for r in csv.DictReader(open(out, encoding="utf-8"))}
    assert float(rows["a"]["ttc_seconds"]) == 300.0
    assert rows["b"]["censored"] == "1" and float(rows["b"]["ttc_seconds"]) == 30 * 86400.0


def test_calibration_tokens_excluded_by_default(tmp_path):
    from datetime import datetime, timezone
    from collector.model import Honeytoken
    from collector.store import TtcStore
    from deploy.export import main
    db = tmp_path / "t.db"
    s = TtcStore(db)
    t0 = datetime(2026, 10, 16, tzinfo=timezone.utc)
    s.register(Honeytoken("github-aws-obvious-1", "aws", "github", "obvious", t0))
    s.register(Honeytoken("calib-aws-0", "aws", "calib", "obvious", t0))
    out = tmp_path / "o.csv"
    main(["--db", str(db), "--out", str(out), "--now", "2026-10-17T00:00:00+00:00"])
    assert "calib" not in out.read_text()
    main(["--db", str(db), "--out", str(out), "--now", "2026-10-17T00:00:00+00:00", "--include-calib"])
    assert "calib-aws-0" in out.read_text()
