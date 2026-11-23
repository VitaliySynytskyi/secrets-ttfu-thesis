"""Аналіз потужності плану експерименту: як часто критерій log-rank виявляє ефект
каналу / типу секрету / помітності (p < 0,05) за різної кількості реплікацій.
Дані генеруються тим самим симулятором (deploy/simulate_campaign.py), що калібрований
за опублікованими розподілами; ефекту помітності в симуляторі немає, тож для неї
частка «виявлень» оцінює хибнопозитивний рівень (має бути ≈ 0,05).

    .venv/Scripts/python.exe -m analysis.power --replicas 3 6 10 --runs 60 --out data/sim/power.json
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

import pandas as pd
import warnings
from lifelines import CoxPHFitter
from lifelines.statistics import multivariate_logrank_test
from scipy.stats import chi2

from deploy.simulate_campaign import run


def cox_type_pvalue(df: pd.DataFrame) -> float:
    """Критерій відношення правдоподібностей для блоку «тип секрету» у моделі Кокса,
    стратифікованій за каналом (ефект каналу не маскує ефект типу)."""
    X = pd.get_dummies(df[["secret_type", "visibility"]], drop_first=True).astype(float)
    X["t"], X["e"], X["channel"] = df.ttc_seconds, 1 - df.censored, df.channel
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        full = CoxPHFitter(penalizer=0.01).fit(X, "t", "e", strata=["channel"])
        red = CoxPHFitter(penalizer=0.01).fit(X.drop(columns=[c for c in X if c.startswith("secret_type_")]),
                                              "t", "e", strata=["channel"])
    k = sum(c.startswith("secret_type_") for c in X)
    return float(chi2.sf(2 * (full.log_likelihood_ - red.log_likelihood_), k))


def power(replicas: int, runs: int, seed0: int = 1000) -> dict:
    hits = {"channel": 0, "secret_type": 0, "visibility": 0}
    cox_type = 0
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        d = Path(d)
        for k in range(runs):
            csv = d / f"r{k}.csv"
            run(csv, d / f"m{k}.csv", d / f"s{k}.db", replicas=replicas, seed=seed0 + k)
            df = pd.read_csv(csv)
            ev = 1 - df.censored
            for col in hits:
                if multivariate_logrank_test(df.ttc_seconds, df[col], ev).p_value < 0.05:
                    hits[col] += 1
            cox_type += cox_type_pvalue(df) < 0.05
    return {"replicas": replicas, "tokens": 32 * replicas, "runs": runs,
            **{f"power_{c}": v / runs for c, v in hits.items()},
            "power_secret_type_cox_stratified": cox_type / runs}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--replicas", type=int, nargs="+", default=[3, 6, 10])
    ap.add_argument("--runs", type=int, default=60)
    ap.add_argument("--out", default="data/sim/power.json")
    a = ap.parse_args()
    res = [power(r, a.runs) for r in a.replicas]
    Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    for r in res:
        print(r)


if __name__ == "__main__":
    main()
