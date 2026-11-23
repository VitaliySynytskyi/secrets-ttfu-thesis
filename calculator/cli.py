# diploma/experiment/calculator/cli.py
from __future__ import annotations
import argparse
import json
from pathlib import Path

from modeling.loader import load_ttc, distinct_strata
from modeling.survival import fit_best_distribution
from modeling.risk import residual_risk, monte_carlo_residual_risk


def _stratified(csv_path, column, values, ttls, impact):
    out = {}
    for v in values:
        durations, events = load_ttc(csv_path, **{column: v})
        if len(durations) < 10 or int(sum(events)) == 0:
            out[v] = {"skipped": "insufficient data"}
            continue
        fit = fit_best_distribution(durations, events)
        out[v] = {"distribution": fit.name,
                  "residual_risk": {str(t): residual_risk(fit.name, fit.params, float(t), impact) for t in ttls}}
    return out


def run(csv_path, ttls, impact: float, out_json) -> dict:
    durations, events = load_ttc(csv_path)
    if len(durations) == 0:
        raise ValueError(f"No data rows loaded from {csv_path} — check path and filters")
    fit = fit_best_distribution(durations, events)
    report = {
        "distribution": fit.name,
        "params": fit.params,
        "aic": fit.all_aic,
        "impact": impact,
        "residual_risk": {
            str(ttl): residual_risk(fit.name, fit.params, float(ttl), impact)
            for ttl in ttls
        },
        "monte_carlo": {
            str(ttl): monte_carlo_residual_risk(fit.name, fit.params, float(ttl), impact)
            for ttl in ttls
        },
    }
    strata = distinct_strata(csv_path)
    report["by_channel"] = _stratified(csv_path, "channel", strata["channels"], ttls, impact)
    report["by_secret_type"] = _stratified(csv_path, "secret_type", strata["secret_types"], ttls, impact)
    report["by_visibility"] = _stratified(csv_path, "visibility", strata["visibilities"], ttls, impact)
    Path(out_json).write_text(json.dumps(report, indent=2, ensure_ascii=False),
                              encoding="utf-8")
    return report


def main() -> int:
    p = argparse.ArgumentParser(description="TTL -> residual risk calculator")
    p.add_argument("csv", help="шлях до ttc.csv")
    p.add_argument("--ttl", type=float, action="append", required=True,
                   help="значення TTL у секундах (можна кілька)")
    p.add_argument("--impact", type=float, default=0.8)
    p.add_argument("--out", default="report.json")
    args = p.parse_args()
    run(args.csv, args.ttl, args.impact, args.out)
    print(f"Saved {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
