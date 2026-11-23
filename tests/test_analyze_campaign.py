# diploma/experiment/tests/test_analyze_campaign.py
import json
from analysis.analyze_campaign import analyze
from deploy.simulate_campaign import run


def test_analyze_produces_all_sections(tmp_path):
    run(tmp_path / "ttc.csv", tmp_path / "man.csv", tmp_path / "sim.db", replicas=2, seed=3)
    r = analyze(tmp_path / "ttc.csv", tmp_path / "out", "test", n_boot=20)
    for key in ("km_by_channel", "logrank_channel", "logrank_visibility", "cox", "fits", "threats"):
        assert key in r
    assert set(r["threats"]) == {"T1", "T2"}
    t1 = r["threats"]["T1"]
    assert 0.0 <= t1["R_cal_ttl60"]["ci_low"] <= t1["R_cal_ttl60"]["median"] <= t1["R_cal_ttl60"]["ci_high"] <= t1["I"]
    for f in ("results.json", "results.md", "fig-km-channel.png", "fig-km-type.png", "fig-risk-ttl.png"):
        assert (tmp_path / "out" / f).exists()
    json.loads((tmp_path / "out" / "results.json").read_text(encoding="utf-8"))
