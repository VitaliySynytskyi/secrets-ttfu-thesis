"""Повний аналіз кампанії honeytoken-ів за методикою розділу 2 (підрозділ 2.5).

Вхід: CSV з колонками token_id, secret_type, channel, visibility, ttc_seconds, censored
(експорт колектора або симуляції). Вихід у --out:
  results.json, results.md          — усі числа (медіани, log-rank, Кокс, AIC, ризики, TTL*)
  fig-km-channel.png, fig-km-type.png — криві Каплана–Маєра
  fig-risk-ttl.png                   — калібрований ризик F(TTL)·I для кожного каналу

    .venv/Scripts/python.exe -m analysis.analyze_campaign data/sim/ttc-sim.csv --out data/sim/analysis --label "СИНТЕТИЧНА вибірка"
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import numpy as np
import pandas as pd
from lifelines import CoxPHFitter, KaplanMeierFitter
from lifelines.statistics import multivariate_logrank_test
from scipy.optimize import brentq

from analysis.power import cox_type_pvalue
from modeling.risk import bootstrap_residual_risk_ci, prob_compromise_within
from modeling.survival import fit_best_distribution

# Загрози курсової, для яких момент витоку визначений (табл. 2.1): канал, експертні L до/після, вплив I.
THREATS = {
    "T1": {"name": "Витік через журнали CI/CD", "channels": ["ci-log"], "L_before": 0.80, "L_after": 0.20, "I": 0.80},
    "T2": {"name": "Секрет у відкритому репозиторії", "channels": ["github", "dotenv"], "L_before": 0.50, "L_after": 0.10, "I": 0.95},
}
TTL_GRID = [60, 900, 3600, 86400]
TTL_DYNAMIC = 60.0          # TTL динамічних секретів на стенді
R_STAR = 0.05               # приклад прийнятного залишкового ризику для оберненої задачі
COLORS = {"github": "#2a78d6", "dotenv": "#eb6834", "ci-log": "#1baf7a", "paste": "#eda100",
          "aws": "#2a78d6", "gcp": "#eb6834", "api": "#1baf7a", "db": "#eda100"}
STYLES = ["-", "--", "-.", ":"]
UA = {"github": "GitHub", "dotenv": ".env у репозиторії", "ci-log": "журнал CI/CD", "paste": "paste-сервіс",
      "aws": "ключ AWS", "gcp": "ключ GCP", "api": "токен API", "db": "облікові дані БД"}


def fmt_dur(s: float) -> str:
    if s is None or (isinstance(s, float) and (math.isinf(s) or math.isnan(s))):
        return "не досягнуто"
    if s < 90:
        return f"{s:.0f} с"
    if s < 5400:
        return f"{s / 60:.1f} хв".replace(".", ",")
    if s < 2 * 86400:
        return f"{s / 3600:.1f} год".replace(".", ",")
    return f"{s / 86400:.1f} доби".replace(".", ",")


def km_stats(df: pd.DataFrame) -> dict:
    kmf = KaplanMeierFitter().fit(df.ttc_seconds, df.event)
    sf = kmf.survival_function_.iloc[:, 0]

    def q(p):  # час, коли використано частку p
        hit = sf[sf <= 1 - p]
        return float(hit.index[0]) if len(hit) else float("inf")

    return {"n": int(len(df)), "used": int(df.event.sum()), "median_s": q(0.5), "p25_s": q(0.25),
            "p75_s": q(0.75), "share_1h": float(1 - kmf.predict(3600.0)),
            "share_24h": float(1 - kmf.predict(86400.0))}


def ttl_star(name, params, target) -> float:
    f = lambda t: prob_compromise_within(name, params, t) - target
    if f(1e8) < 0:
        return float("inf")
    return float(brentq(f, 1e-3, 1e8))


def plot_km(df, col, levels, path, label):
    fig, ax = plt.subplots(figsize=(8, 4.6))
    for i, lv in enumerate(levels):
        sub = df[df[col] == lv]
        if sub.empty:
            continue
        kmf = KaplanMeierFitter().fit(sub.ttc_seconds, sub.event, label=UA.get(lv, lv))
        kmf.plot_survival_function(ax=ax, ci_show=False, color=COLORS.get(lv), ls=STYLES[i % 4], lw=2)
    ax.set_xscale("log")
    ax.set_xlim(10, 40 * 86400)
    ticks = [60, 3600, 86400, 7 * 86400, 30 * 86400]
    ax.set_xticks(ticks)
    ax.set_xticklabels(["1 хв", "1 год", "1 доба", "7 діб", "30 діб"])
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.1f}".replace(".", ",")))
    ax.set_ylim(0, 1.02)
    ax.set_xlabel("Час після публікації (логарифмічна шкала)")
    ax.set_ylabel("Частка ще не використаних токенів S(t)")
    ax.grid(True, color="#e6e6e6", lw=0.6)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.legend(frameon=False, loc="lower left")
    ax.set_title(label, fontsize=10, color="#6b6b6b", loc="right")
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def plot_risk(fits, path, label, impact=0.8):
    t = np.logspace(0, math.log10(30 * 86400), 300)
    fig, ax = plt.subplots(figsize=(8, 4.6))
    for i, (ch, fit) in enumerate(fits.items()):
        ax.plot(t, [prob_compromise_within(fit.name, fit.params, x) * impact for x in t],
                color=COLORS.get(ch), ls=STYLES[i % 4], lw=2, label=UA.get(ch, ch))
    ax.axvline(60, color="#6b6b6b", lw=0.8, ls=":")
    ax.text(66, 0.77, "TTL = 60 с", fontsize=9, color="#6b6b6b")
    ax.set_xscale("log")
    ax.set_xticks([1, 60, 3600, 86400, 30 * 86400])
    ax.set_xticklabels(["1 с", "1 хв", "1 год", "1 доба", "30 діб"])
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.1f}".replace(".", ",")))
    ax.set_ylim(0, 0.82)
    ax.set_xlabel("Термін дії облікових даних TTL (логарифмічна шкала)")
    ax.set_ylabel(f"Залишковий ризик F(TTL) · I, I = {impact}".replace(".", ","))
    ax.grid(True, color="#e6e6e6", lw=0.6)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.legend(frameon=False, loc="upper left")
    ax.set_title(label, fontsize=10, color="#6b6b6b", loc="right")
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def analyze(csv_path, out_dir, label="", n_boot=200, seed=0) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(csv_path)
    df["event"] = 1 - df["censored"].astype(int)
    df["ttc_seconds"] = df["ttc_seconds"].clip(lower=1e-3)
    res: dict = {"label": label, "n_tokens": int(len(df)), "n_used": int(df.event.sum())}

    for col in ("channel", "secret_type", "visibility"):
        res[f"km_by_{col}"] = {lv: km_stats(g) for lv, g in df.groupby(col)}
        lr = multivariate_logrank_test(df.ttc_seconds, df[col], df.event)
        res[f"logrank_{col}"] = {"chi2": float(lr.test_statistic), "df": int(lr.degrees_of_freedom),
                                 "p": float(lr.p_value)}

    res["cox_stratified_type_p"] = cox_type_pvalue(df)
    X = pd.get_dummies(df[["channel", "secret_type", "visibility"]].astype("category"), drop_first=False)
    base = ["channel_github", "secret_type_aws", "visibility_buried"]
    X = X.drop(columns=[c for c in base if c in X.columns]).astype(float)
    X["ttc_seconds"], X["event"] = df.ttc_seconds, df.event
    cph = CoxPHFitter(penalizer=0.01).fit(X, "ttc_seconds", "event")
    s = cph.summary
    res["cox"] = {k: {"HR": float(s.loc[k, "exp(coef)"]), "ci_low": float(s.loc[k, "exp(coef) lower 95%"]),
                      "ci_high": float(s.loc[k, "exp(coef) upper 95%"]), "p": float(s.loc[k, "p"])}
                  for k in s.index}
    res["cox_baseline"] = "GitHub, ключ AWS, buried"

    fits = {}
    res["fits"] = {}
    for ch, g in df.groupby("channel"):
        if g.event.sum() == 0:  # повністю цензурована страта: параметрична модель не визначена
            res["fits"][ch] = {"best": None, "n": int(len(g)), "events": 0}
            continue
        fit = fit_best_distribution(g.ttc_seconds.to_numpy(), g.event.to_numpy())
        fits[ch] = fit
        res["fits"][ch] = {"best": fit.name, "params": fit.params, "aic": fit.all_aic,
                           "F": {str(t): prob_compromise_within(fit.name, fit.params, t) for t in TTL_GRID}}

    res["threats"] = {}
    for tid, th in THREATS.items():
        g = df[df.channel.isin(th["channels"])]
        if g.event.sum() == 0:
            # Жодної події: бутстреп параметричної моделі не збігається. Точна одностороння
            # 95 % верхня межа для F(t) при t ≤ мінімального вікна спостереження: 1 − 0,05^(1/n).
            n = int(len(g))
            res["threats"][tid] = {**th, "fit": None, "n": n, "events": 0,
                                   "followup_min_s": float(g.ttc_seconds.min()),
                                   "F_upper95": 1 - 0.05 ** (1 / n),
                                   "R_upper95": (1 - 0.05 ** (1 / n)) * th["I"],
                                   "R_expert_before": th["L_before"] * th["I"],
                                   "R_expert_after": th["L_after"] * th["I"]}
            continue
        ci = bootstrap_residual_risk_ci(g.ttc_seconds.to_numpy(), g.event.to_numpy(), [TTL_DYNAMIC, 30 * 86400],
                                        th["I"], n_boot=n_boot, seed=seed)
        fit = fit_best_distribution(g.ttc_seconds.to_numpy(), g.event.to_numpy())
        res["threats"][tid] = {
            **th, "fit": fit.name,
            "R_expert_after": th["L_after"] * th["I"],
            "F_ttl60": prob_compromise_within(fit.name, fit.params, TTL_DYNAMIC),
            "R_cal_ttl60": ci[str(TTL_DYNAMIC)],
            "R_expert_before": th["L_before"] * th["I"],
            "R_cal_static_30d": ci[str(30 * 86400)],
            "TTL_star_s": ttl_star(fit.name, fit.params, R_STAR / th["I"]),
        }

    plot_km(df, "channel", ["github", "dotenv", "ci-log", "paste"], out / "fig-km-channel.png", label)
    plot_km(df, "secret_type", ["aws", "gcp", "api", "db"], out / "fig-km-type.png", label)
    plot_risk(fits, out / "fig-risk-ttl.png", label)
    (out / "results.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "results.md").write_text(to_markdown(res), encoding="utf-8")
    return res


def _n(x, d=3):
    return f"{x:.{d}f}".replace(".", ",")


def to_markdown(r: dict) -> str:
    L = [f"# Результати аналізу кампанії ({r['label']})", "",
         f"Токенів: {r['n_tokens']}, використано до кінця спостереження: {r['n_used']}.", "",
         "## Медіана та перцентилі TTFU за каналом (Каплан–Маєр)", "",
         "| Канал | n | використано | 25 % | медіана | 75 % | частка за 1 год | за 24 год |", "|---|---|---|---|---|---|---|---|"]
    for k, v in r["km_by_channel"].items():
        L.append(f"| {UA.get(k, k)} | {v['n']} | {v['used']} | {fmt_dur(v['p25_s'])} | {fmt_dur(v['median_s'])} | "
                 f"{fmt_dur(v['p75_s'])} | {_n(v['share_1h'], 2)} | {_n(v['share_24h'], 2)} |")
    L += ["", "## Те саме за типом секрету", "", "| Тип | n | використано | медіана | частка за 1 год |", "|---|---|---|---|---|"]
    for k, v in r["km_by_secret_type"].items():
        L.append(f"| {UA.get(k, k)} | {v['n']} | {v['used']} | {fmt_dur(v['median_s'])} | {_n(v['share_1h'], 2)} |")
    L += ["", "## Критерій log-rank (H1–H3)", "", "| Фактор | χ² | ступені свободи | p |", "|---|---|---|---|"]
    for col, nm in [("channel", "канал (H1)"), ("secret_type", "тип секрету (H2)"), ("visibility", "помітність (H3)")]:
        v = r[f"logrank_{col}"]
        L.append(f"| {nm} | {_n(v['chi2'], 2)} | {v['df']} | {v['p']:.2g} |")
    L.append(f"| тип секрету, модель Кокса зі стратами за каналом (H2) | | 3 | {r['cox_stratified_type_p']:.2g} |")
    L += ["", f"## Модель Кокса (база: {r['cox_baseline']})", "", "| Змінна | HR | 95 % ДІ | p |", "|---|---|---|---|"]
    for k, v in r["cox"].items():
        L.append(f"| {k} | {_n(v['HR'], 2)} | {_n(v['ci_low'], 2)}–{_n(v['ci_high'], 2)} | {v['p']:.2g} |")
    L += ["", "## Параметрична модель за каналом (вибір за AIC) і F(TTL)", "",
          "| Канал | модель | F(60 с) | F(15 хв) | F(1 год) | F(1 доба) |", "|---|---|---|---|---|---|"]
    for k, v in r["fits"].items():
        if v["best"] is None:
            L.append(f"| {UA.get(k, k)} | — (0 подій з {v['n']}) | — | — | — | — |")
            continue
        F = v["F"]
        L.append(f"| {UA.get(k, k)} | {v['best']} | {_n(F['60'])} | {_n(F['900'])} | {_n(F['3600'])} | {_n(F['86400'])} |")
    L += ["", "## Калібрований ризик проти експертного", "",
          "| Загроза | R експ. до | R калібр. (статичний, 30 діб) | R експ. після (TTL 60 с) | R калібр. (TTL 60 с), 95 % ДІ | TTL* для R* = 0,05 |",
          "|---|---|---|---|---|---|"]
    for k, v in r["threats"].items():
        if v.get("events") == 0:
            L.append(f"| {k}. {v['name']} | {_n(v['R_expert_before'])} | 0 подій з {v['n']} за {fmt_dur(v['followup_min_s'])}; "
                     f"R ≤ {_n(v['R_upper95'])} (95 %) | {_n(v['R_expert_after'])} | ≤ {_n(v['R_upper95'])} | — |")
            continue
        c60, cst = v["R_cal_ttl60"], v["R_cal_static_30d"]
        L.append(f"| {k}. {v['name']} | {_n(v['R_expert_before'])} | {_n(cst['median'])} ({_n(cst['ci_low'])}–{_n(cst['ci_high'])}) | "
                 f"{_n(v['R_expert_after'])} | {_n(c60['median'])} ({_n(c60['ci_low'])}–{_n(c60['ci_high'])}) | {fmt_dur(v['TTL_star_s'])} |")
    return "\n".join(L) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--out", required=True)
    ap.add_argument("--label", default="")
    ap.add_argument("--n-boot", type=int, default=200)
    a = ap.parse_args()
    r = analyze(a.csv, a.out, a.label, n_boot=a.n_boot)
    print((Path(a.out) / "results.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
