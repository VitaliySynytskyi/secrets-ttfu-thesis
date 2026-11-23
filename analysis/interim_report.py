"""Проміжний звіт кампанії (до кінця вікна спостереження): графік + таблиця для демонстрації.

Бере знімок data/campaign/<дата>/ (pull-data.sh), відкидає пілот (репліки -0) і калібрувальні
токени, малює накопичену частку використаних токенів за каналами й зводить таблицю
канал × тип. Цифри ПРОМІЖНІ — стратифіковані фіти тут навмисно не робляться (замало подій).

    .venv/Scripts/python.exe -m analysis.interim_report --out ../../output/demo-2026-10-28
    .venv/Scripts/python.exe -m analysis.interim_report data/campaign/20261026T1800Z --out ...
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import pandas as pd
from lifelines import KaplanMeierFitter

from analysis.analyze_campaign import COLORS, UA, fmt_dur

HERE = Path(__file__).resolve().parents[1]
CHANNELS = ["github", "dotenv", "paste", "ci-log"]
TYPES = ["aws", "gcp", "db", "api"]
TYPE_HDR = {"aws": "AWS", "gcp": "GCP", "db": "БД", "api": "API"}
STYLES = {"github": "-", "dotenv": "--", "paste": "-.", "ci-log": ":"}
AI_EVENTS = {"ListFoundationModels", "GetFoundationModelAvailability", "PutUseCaseForModelAccess",
             "PutFoundationModelEntitlement", "InvokeModel", "InvokeModelWithResponseStream",
             "Converse", "ConverseStream"}


def load(snapshot: Path) -> pd.DataFrame:
    df = pd.read_csv(snapshot / "ttc.csv")
    rep = df.token_id.str.rsplit("-", n=1).str[-1]
    df = df[rep.str.isdigit() & (rep != "0") & (df.channel != "calib")].copy()
    df["event"] = 1 - df.censored
    return df


def bedrock_tokens(snapshot: Path, users_csv: Path) -> set[str]:
    """Токени, ключами яких викликали Amazon Bedrock (LLMjacking), за журналом CloudTrail."""
    raw = snapshot / "raw-cloud-events.jsonl"
    if not raw.exists() or not users_csv.exists():
        return set()
    with open(users_csv, encoding="utf-8") as fh:
        key2tok = {row[2]: row[0] for row in csv.reader(fh) if len(row) >= 3}
    hit = set()
    for line in open(raw, encoding="utf-8"):
        p = json.loads(line).get("payload", {})
        if p.get("EventName") in AI_EVENTS and p.get("AccessKeyId") in key2tok:
            hit.add(key2tok[p["AccessKeyId"]])
    return hit


def snapshot_time(snapshot: Path) -> datetime:
    return datetime.strptime(snapshot.name.rstrip("/"), "%Y%m%dT%H%MZ")


def plot(df: pd.DataFrame, path: Path, label: str) -> None:
    fig, ax = plt.subplots(figsize=(8, 4.6))
    for ch in CHANNELS:
        sub = df[df.channel == ch]
        kmf = KaplanMeierFitter().fit(sub.ttc_seconds, sub.event)
        cdf = 1 - kmf.survival_function_.iloc[:, 0]
        t_end = float(sub.ttc_seconds.min() if sub.event.sum() == 0 else sub.ttc_seconds.max())
        cdf = cdf[cdf.index <= t_end]
        xs = [10.0] + [max(float(t), 10.0) for t in cdf.index[1:]] + [t_end]
        ys = [0.0] + list(cdf.values[1:]) + [float(cdf.values[-1])]
        ax.step(xs, ys, where="post", color=COLORS[ch], ls=STYLES[ch], lw=2,
                label=f"{UA[ch]} ({int(sub.event.sum())}/{len(sub)})")
    first = df[df.event == 1].ttc_seconds.min()
    ax.annotate(f"перше використання:\n{fmt_dur(first)} після публікації", (first, 1 / 24),
                xytext=(-10, 150), textcoords="offset points", fontsize=8, color="#52514e",
                arrowprops=dict(arrowstyle="-", color="#9a9a96", lw=0.8))
    ax.set_xscale("log")
    ax.set_xlim(10, 10 * 86400)
    ax.set_xticks([60, 900, 3600, 6 * 3600, 86400, 3 * 86400, 7 * 86400])
    ax.set_xticklabels(["1 хв", "15 хв", "1 год", "6 год", "1 доба", "3 доби", "7 діб"])
    ax.minorticks_off()
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0%}".replace(".", ",")))
    ax.set_ylim(0, 0.55)
    ax.set_xlabel("Час після публікації (логарифмічна шкала)")
    ax.set_ylabel("Частка використаних токенів")
    ax.grid(True, axis="y", color="#e6e6e6", lw=0.6)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.legend(frameon=False, loc="upper left", fontsize=8, title="Канал (використано/опубліковано)",
              title_fontsize=8)
    ax.set_title(label, fontsize=9, color="#6b6b6b", loc="right")
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def table(df: pd.DataFrame, bedrock: set[str]) -> list[dict]:
    rows = []
    for ch in CHANNELS + ["Разом"]:
        sub = df if ch == "Разом" else df[df.channel == ch]
        row = {"Канал": "Разом" if ch == "Разом" else UA[ch]}
        for ty in TYPES:
            s = sub[sub.secret_type == ty]
            row[TYPE_HDR[ty]] = f"{int(s.event.sum())}/{len(s)}"
        row["Разом"] = f"{int(sub.event.sum())}/{len(sub)}"
        used = sub[sub.event == 1].ttc_seconds
        row["Найшвидше використання"] = fmt_dur(float(used.min())) if len(used) else "—"
        row["Нейтралізовано платформою"] = f"{int(sub.exposed_seconds.notna().sum())}/{len(sub)}"
        row["Спроби Bedrock"] = str(len(set(sub.token_id) & bedrock))
        rows.append(row)
    return rows


def to_markdown(rows: list[dict], caption: str, note: str) -> str:
    hdr = list(rows[0])
    out = [caption, "", "| " + " | ".join(hdr) + " |", "|" + "|".join(["---"] * len(hdr)) + "|"]
    out += ["| " + " | ".join(r[h] for h in hdr) + " |" for r in rows]
    return "\n".join(out + ["", note, ""])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("snapshot", nargs="?", type=Path, help="data/campaign/<дата>/ (за замовчуванням — найновіший)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--users", type=Path, default=Path.home() / ".config/ttc/aws/users.csv",
                    help="мапінг token_id,IAM-user,AccessKeyId (поза репозиторієм)")
    a = ap.parse_args()
    snap = a.snapshot or max((HERE / "data/campaign").iterdir(), key=lambda p: p.name)
    a.out.mkdir(parents=True, exist_ok=True)

    df = load(snap)
    bedrock = bedrock_tokens(snap, a.users)
    when = snapshot_time(snap).strftime("%d.%m.%Y %H:%M UTC")
    label = f"Проміжні дані, станом на {when}"
    plot(df, a.out / "fig-interim-channel.png", label)
    rows = table(df, bedrock)
    with open(a.out / "table-interim.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    note = (f"Примітка. Комірки «тип» — використано/опубліковано токенів (`use`). Вікно спостереження "
            f"на {when}: від {fmt_dur(float(df.ttc_seconds[df.event == 0].min()))} до "
            f"{fmt_dur(float(df.ttc_seconds.max()))} залежно від часу публікації; кінець вікна — 15.11.2026. "
            f"«Нейтралізовано платформою» — подія `exposed` (GitHub secret scanning → карантин AWS / "
            f"вимкнення ключа Google), окремо від використання. «Спроби Bedrock» — токени, ключами яких "
            f"викликали Amazon Bedrock (LLMjacking), за журналом CloudTrail. Пілот (8 токенів) і "
            f"калібрувальні токени не враховано.")
    md = to_markdown(rows, f"Таблиця — Проміжні результати кампанії honeytoken-ів ({when})", note)
    (a.out / "table-interim.md").write_text(md, encoding="utf-8")
    print(md)
    print(f"-> {a.out}  (знімок {snap.name})")


if __name__ == "__main__":
    main()
