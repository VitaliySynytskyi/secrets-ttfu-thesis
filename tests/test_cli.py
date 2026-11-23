# diploma/experiment/tests/test_cli.py
import json
from synthetic import sample_weibull_ttc
from calculator.cli import run


def test_cli_end_to_end_from_csv(tmp_path):
    # підготувати ttc.csv із синтетики
    durations, events = sample_weibull_ttc(n=2000, lam=3600.0, rho=1.2, seed=5)
    csv = tmp_path / "ttc.csv"
    lines = ["token_id,secret_type,channel,ttc_seconds,censored"]
    for i, (d, e) in enumerate(zip(durations, events)):
        lines.append(f"t{i},aws,github,{d},{0 if e == 1 else 1}")
    csv.write_text("\n".join(lines), encoding="utf-8")

    out = tmp_path / "report.json"
    run(csv_path=csv, ttls=[60, 3600], impact=0.8, out_json=out)
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["distribution"] in {"weibull", "exponential", "lognormal"}
    assert "60" in report["residual_risk"]
    assert report["residual_risk"]["60"] < report["residual_risk"]["3600"]
    mc = report["monte_carlo"]["60"]
    assert {"median", "ci_low", "ci_high"} <= set(mc)
    assert mc["ci_low"] <= mc["median"] <= mc["ci_high"]
    assert "by_channel" in report and "github" in report["by_channel"]
    assert "by_secret_type" in report and "aws" in report["by_secret_type"]
    assert report["by_visibility"] == {}  # у датасеті без колонки visibility страт немає


def test_cli_stratifies_by_visibility(tmp_path):
    durations, events = sample_weibull_ttc(n=400, lam=3600.0, rho=1.2, seed=7)
    csv = tmp_path / "ttc.csv"
    lines = ["token_id,secret_type,channel,visibility,ttc_seconds,censored"]
    for i, (d, e) in enumerate(zip(durations, events)):
        vis = "obvious" if i % 2 else "buried"
        lines.append(f"t{i},aws,github,{vis},{d},{0 if e == 1 else 1}")
    csv.write_text("\n".join(lines), encoding="utf-8")
    report = run(csv_path=csv, ttls=[60], impact=0.8, out_json=tmp_path / "r.json")
    assert set(report["by_visibility"]) == {"obvious", "buried"}
    assert "residual_risk" in report["by_visibility"]["obvious"]
