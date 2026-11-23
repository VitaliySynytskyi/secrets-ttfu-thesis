"""Усі генеровані рисунки магістерської роботи в одному стилі для друку.

    python figures/make_figures.py                          # синтетичний знімок data/sample/
    python figures/make_figures.py data/campaign/<знімок>   # власний знімок кампанії

Шляхи адаптовано для цього репозиторію: корінь репозиторію = каталог коду експерименту,
рисунки пишуться у figures/out/. Реальний знімок кампанії до репозиторію не входить, тож
за замовчуванням використовується синтетична вибірка data/sample/ (deploy/simulate_campaign.py);
підписи хвиль (26.10, 03–09.11) на часових діаграмах стосуються реальної кампанії.

Аргумент — каталог знімка кампанії (за замовчуванням data/sample/). З нього беруться
ttc-campaign.csv (часові діаграми, криві Каплана–Маєра, F(TTL)) і ttc.csv (накопичена частка,
та сама вибірка, що в analysis.interim_report). Обчислення ті самі, що в analysis.analyze_campaign
та analysis.interim_report; тут лише оформлення для друку: розмір полотна дорівнює ширині рисунка
на сторінці (частка від 17 см з атрибута width у masters/*.md), тож розмір шрифту в пунктах
дорівнює розміру у друці (мінімум 8 пт). Шрифт Segoe UI, 300 dpi, без заголовків усередині
рисунка (назва — у підписі під рисунком за ДСТУ), десяткова кома на осях.

Рисунки стенду (скриншоти) не генеруються; дерево атак малюється тут (раніше — Graphviz,
analysis/attack-trees/01-static-secret-pipeline.dot, горизонтальна розкладка) і кладеться у
figures/out/stand/ (у вихідному репозиторії роботи — masters/figures/stand/).
"""
from __future__ import annotations

import argparse
import math
import sys
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from matplotlib.ticker import FuncFormatter
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT                      # у цьому репозиторії код експерименту лежить у корені
sys.path.insert(0, str(EXP))
DEFAULT_SNAP = EXP / "data/sample"
OUT = Path(__file__).parent / "out"

FONT = ["Segoe UI", "DejaVu Sans"]
FS, FS_S = 9, 8.5            # основний і мінімальний розмір шрифту, пт (у друці)
plt.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": FONT, "font.size": FS,
    "axes.labelsize": FS, "xtick.labelsize": FS_S, "ytick.labelsize": FS_S,
    "legend.fontsize": FS_S, "axes.linewidth": 0.8, "savefig.dpi": 300,
})
INK, MUTED = "#1f1f1f", "#6b6b6b"
BLUE, ORANGE, AQUA, RED = "#2a78d6", "#eb6834", "#1baf7a", "#c8442f"
DAY = 86400
TEXT_W_CM = 17.0
COMMA1 = FuncFormatter(lambda v, _: f"{v:.1f}".replace(".", ","))


def width_in(pct: float) -> float:
    """Ширина рисунка на сторінці, дюйми, для атрибута width=pct% у masters/*.md."""
    return pct / 100 * TEXT_W_CM / 2.54


def save(fig, path: Path, pct: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=300, bbox_inches="tight", pad_inches=0.04, facecolor="white")
    plt.close(fig)
    from PIL import Image
    w, h = Image.open(path).size
    scale = width_in(pct) * 300 / w
    print(f"{path.relative_to(ROOT)}: {w}x{h}px, width={pct}% -> масштаб {scale:.2f}, "
          f"мін. шрифт у друці ≈ {FS_S * scale:.1f} пт")


def box(ax, x, y, w, h, text="", ec=INK, fc="#ffffff", fs=FS, bold=False, lw=1.1, r=0.06, **kw):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0.0,rounding_size={r}",
                                lw=lw, ec=ec, fc=fc, **kw))
    if text:
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs,
                fontweight="bold" if bold else "normal", color=INK, linespacing=1.2)


def arrow(ax, x1, y1, x2, y2, color=INK, ls="-", lw=1.1):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-|>", lw=lw, color=color, ls=ls, shrinkA=0, shrinkB=0,
                                mutation_scale=9))


def canvas(w, h):
    """Полотно в дюймах з координатами в дюймах (зручно для схем)."""
    fig = plt.figure(figsize=(w, h))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, w); ax.set_ylim(0, h); ax.axis("off")
    return fig, ax


# ----------------------------------------------------------------------------- схеми розділів 1–3

def fig_architecture(pct=95):
    W = width_in(pct)
    fig, ax = canvas(W, 3.75)
    bw, bh, g = 0.86, 1.05, 0.13
    for x0, ec, fc, title, items in [
        (0.04, BLUE, "#f3f8fe", "Захисний контур (динамічні секрети)",
         ["Kubernetes\n(kind):\nдодаток,\nService-\nAccount", "HashiCorp\nVault\nK8s Auth,\nDB Engine",
          "PostgreSQL\nролі з\nTTL = 60 с"]),
        (W / 2 + 0.06, ORANGE, "#fef5f1", "Вимірювальний контур (honeytoken)",
         ["Приманки\nбез прав\n(реєстр, t₀)", "Канали:\nGitHub, .env,\npaste,\nжурнал CI/CD",
          "Детектори\nі колектор\n(t₁): FastAPI,\nSQLite"]),
    ]:
        cw = W / 2 - 0.1
        box(ax, x0, 2.0, cw, 1.7, ec=ec, fc=fc, ls="--", r=0.1)
        ax.text(x0 + cw / 2, 3.5, title, ha="center", va="center", fontsize=FS, fontweight="bold")
        inner = 3 * bw + 2 * g
        bx = [x0 + (cw - inner) / 2 + i * (bw + g) for i in range(3)]
        for x, t in zip(bx, items):
            box(ax, x, 2.15, bw, bh * 1.12, t, fs=FS_S)
        for a, b in zip(bx[:-1], bx[1:]):
            arrow(ax, a + bw, 2.15 + bh * 0.56, b, 2.15 + bh * 0.56)
        if x0 < 1:
            left_c = bx[1] + bw / 2
        else:
            right_c = bx[2] + bw / 2
    mw, sw, y0, hh = 1.95, 1.05, 0.08, 1.0
    xm = W / 2 - sw / 2
    xl, xr = xm - 0.25 - mw, xm + sw + 0.25
    box(ax, xl, y0, mw, hh, "Модель загроз\nдерево атак T1–T5\nматриця NIST SP 800-30")
    box(ax, xr, y0, mw, hh, "Аналіз виживання\nKM, log-rank, Кокс,\nВейбулл + AIC → F(t)")
    box(ax, xm, y0, sw, hh, "Калібрований\nризик\nF(TTL)·I", ec=AQUA, fc="#effaf5", bold=True)
    arrow(ax, xl + mw, y0 + hh / 2, xm, y0 + hh / 2)
    arrow(ax, xr, y0 + hh / 2, xm + sw, y0 + hh / 2)
    arrow(ax, xl + mw / 2, 2.0, xl + mw / 2, y0 + hh)
    ax.text(xl + mw / 2 + 0.07, 1.55, "TTL", fontsize=FS, color=MUTED, va="center")
    arrow(ax, right_c, 2.0, xr + mw / 2, y0 + hh)
    x_line = right_c + (xr + mw / 2 - right_c) * (2.0 - 1.55) / (2.0 - y0 - hh)
    ax.text(x_line + 0.1, 1.55, "TTFU = t₁ − t₀", fontsize=FS, color=MUTED, va="center")
    save(fig, OUT / "fig-01-01-architecture.png", pct)


def fig_measurement(pct=95):
    W = width_in(pct)
    fig, ax = canvas(W, 1.75)
    labels = ["1. Реєстр\nseed: token_id,\nтип, канал,\nпомітність",
              "2. Генерація\nприманки:\nобліковий запис\nбез прав",
              "3. Публікація\nу канал;\nфіксація t₀",
              "4. Звернення\nсканера →\nдетектор\n(журнал аудиту,\nused_at = t₁)",
              "5. Експорт CSV\nttc_seconds,\ncensored →\nаналіз\nвиживання"]
    g = 0.2
    bw = (W - 0.08 - 4 * g) / 5
    xs = [0.04 + i * (bw + g) for i in range(5)]
    for x, t in zip(xs, labels):
        box(ax, x, 0.42, bw, 1.28, t)
    for a, b in zip(xs[:-1], xs[1:]):
        arrow(ax, a + bw, 1.06, b, 1.06)
    ax.text(W / 2, 0.16, "Токени без звернення до кінця вікна спостереження → цензуровані (censored = 1)",
            ha="center", va="center", fontsize=FS, color=MUTED, style="italic")
    save(fig, OUT / "fig-01-02-measurement.png", pct)


def fig_weibull(pct=75):
    t = np.linspace(0.001, 3, 400)
    fig, ax = plt.subplots(figsize=(width_in(pct) - 0.05, 3.0))
    for k, c, ls, lab in [(0.5, BLUE, "-", "k = 0,5 (спадна інтенсивність)"),
                          (1.0, ORANGE, "--", "k = 1 (експоненційний)"),
                          (2.0, AQUA, "-.", "k = 2 (зростаюча інтенсивність)")]:
        ax.plot(t, np.exp(-(t) ** k), color=c, lw=1.8, ls=ls, label=lab)
    ax.axhline(0.5, color=MUTED, lw=0.8, ls=":")
    ax.text(2.97, 0.52, "S(t) = 0,5 – медіана", ha="right", va="bottom", fontsize=FS_S, color=MUTED)
    ax.set_xlabel("Час після публікації t, умовні одиниці (t/λ)")
    ax.set_ylabel("Частка ще не використаних\nсекретів S(t)")
    ax.set_xlim(0, 3); ax.set_ylim(0, 1.02)
    ax.xaxis.set_major_formatter(COMMA1); ax.yaxis.set_major_formatter(COMMA1)
    ax.grid(True, color="#e6e6e6", lw=0.6)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.legend(frameon=False, loc="upper right")
    save(fig, OUT / "fig-02-03-weibull.png", pct)


def fig_attack_tree(pct=100):
    """Дерево атак T1–T5 (зміст — analysis/attack-trees/01-static-secret-pipeline.dot), вертикальна розкладка."""
    W = width_in(pct)
    OR_C, LEAF_C, LOW_C, CRIT_C, ROOT_C = "#ffa07a", "#ffffe0", "#90ee90", "#ffa500", "#fa8072"
    branches = [
        ("1. Витік секрету\nчерез логи CI/CD\n[OR]",
         [("1.1 Секрет\nвиводиться у\nstdout/stderr", "H", 0.8),
          ("1.2 Артефакт\nзбірки містить\nenv-змінні", "M", 0.5),
          ("1.3 Лог доступний\nпублічно або\nзловмиснику", "M", 0.5)]),
        ("2. Отримання\nсекрету з\nрепозиторію [OR]",
         [("2.1 Хардкод\nсекрету у\ngit-комміті", "H", 0.8),
          ("2.2 Секрет у .env\nфайлі без\n.gitignore", "M", 0.5),
          ("2.3 Компрометація\nпубл./приват.\nтокена\nGitHub/GitLab", "M", 0.5)]),
        ("3. Перехоплення\nenv-змінних\nCI/CD [OR]",
         [("3.1 PPE — отруєний\nконвеєр виконання\n(зловмисний PR)", "M", 0.5),
          ("3.2 Компрометація\nраннера або\nагента", "L", 0.2),
          ("3.3 SSRF до IMDS/\nметаданих хмари", "L", 0.2)]),
        ("4. Компрометація\nSecret Zero\n[AND]",
         [("4.1 Отримання\nдовгострокового\nкореневого\nтокена", "M", 0.5),
          ("4.2 Відсутність\nротації або\nаудиту", "H", 0.8)]),
        ("5. Replay-атака\nз вкраденим\nсекретом [AND]",
         [("5.1 Секрет не має\nобмеженого TTL", "VH", 0.95),
          ("5.2 Відсутня\nавтоматична\nревокація", "H", 0.8)]),
    ]
    H = 5.28
    fig, ax = canvas(W, H)
    colw = W / 5
    bw = colw - 0.06
    LFS, IND = 8, 0.17       # шрифт листів (пт) і відступ листа від «хребта» гілки (дюйми)
    # корінь
    rw, rh, ry = 3.2, 0.5, H - 0.55
    box(ax, (W - rw) / 2, ry, rw, rh, "Компрометація статичного секрету\nв CI/CD-конвеєрі [OR]",
        fc=ROOT_C, bold=True, lw=1.6)
    bus = ry - 0.2
    ax.plot([W / 2, W / 2], [ry, bus], color=INK, lw=1.0)
    ax.plot([colw / 2, W - colw / 2], [bus, bus], color=INK, lw=1.0)
    by, bh = bus - 0.2 - 0.62, 0.62
    leaf_h = lambda n: 0.142 * n + 0.1
    for i, (blab, leaves) in enumerate(branches):
        cx = colw * i + colw / 2
        x0 = cx - bw / 2
        arrow(ax, cx, bus, cx, by + bh)
        box(ax, x0, by, bw, bh, blab, fc=OR_C, fs=FS_S)
        spine_x = x0 + 0.07
        y = by - 0.16
        last_mid = None
        for txt, lvl, p in leaves:
            lh = leaf_h(txt.count("\n") + 2)
            y -= lh
            fc = CRIT_C if p >= 0.9 else LOW_C if p < 0.3 else LEAF_C
            lab = f"{txt}\np = {str(p).replace('.', ',')} ({lvl})"
            box(ax, x0 + IND, y, bw - IND, lh, lab, fc=fc, fs=LFS)
            last_mid = y + lh / 2
            arrow(ax, spine_x, last_mid, x0 + IND, last_mid)
            y -= 0.12
        ax.plot([spine_x, spine_x], [by, last_mid], color=INK, lw=1.0)
    # легенда
    ly, lh = 0.08, 0.95
    box(ax, 0.02, ly, W - 0.04, lh, ec=MUTED, ls=":", r=0.04)
    ax.text(0.12, ly + lh - 0.15, "Легенда. Шкала імовірностей листів p: L = 0,2; M = 0,5; H = 0,8; VH = 0,95",
            fontsize=FS_S, va="center", fontweight="bold")
    items = [(OR_C, "OR-вузол: достатньо\nодного дочірнього\nвузла"),
             (OR_C, "AND-вузол:\nпотрібні всі\nдочірні вузли"),
             (LEAF_C, "Листовий вузол\n(атомарна атака)"),
             (LOW_C, "Низький ризик\np < 0,3"),
             (CRIT_C, "Критичний ризик\np ≥ 0,9")]
    iw = (W - 0.24 - 4 * 0.08) / 5
    for k, (fc, t) in enumerate(items):
        box(ax, 0.12 + k * (iw + 0.08), ly + 0.08, iw, 0.56, t, fc=fc, fs=LFS)
    save(fig, OUT / "stand/fig-07-01-attack-tree.png", pct)


def fig_detectors(pct=100):
    W = width_in(pct)
    fig, ax = canvas(W, 5.3)
    lanes = ["Дослідник\n(реєстр, t₀)", "Канал\n(GitHub, .env,\npaste, лог CI)", "Сканер\nзловмисника",
             "Хмара / пастка\n(CloudTrail,\nAudit Logs,\nPostgres, API)", "VM колектора\n(опитувач +\nколектор)"]
    colw = W / 5
    xs = [colw * i + colw / 2 for i in range(5)]
    hw = colw - 0.12
    for x, t in zip(xs, lanes):
        box(ax, x - hw / 2, 4.55, hw, 0.72, t, fs=FS_S)
        ax.plot([x, x], [0.62, 4.55], color="#c9c9c9", lw=0.9, ls="--", zorder=0)

    def msg(i, j, y, text, color=INK, dashed=False, tx=None, ha="center"):
        arrow(ax, xs[i], y, xs[j], y, color=color, ls="--" if dashed else "-", lw=1.2)
        ax.text(tx if tx is not None else (xs[i] + xs[j]) / 2, y + 0.06, text, ha=ha, va="bottom",
                fontsize=FS_S, color=color, linespacing=1.15,
                bbox=dict(boxstyle="square,pad=0.08", fc="white", ec="none"))

    msg(0, 1, 3.95, "1. публікація приманки;\nt₀ = час git push / прогону / допису", tx=0.08, ha="left")
    msg(2, 1, 3.4, "2. сканує новий вміст")
    msg(1, 2, 3.0, "знаходить секрет", dashed=True)
    msg(2, 3, 2.35, "3. будь-який виклик / вхід /\nзапит із секретом", RED)
    msg(3, 2, 1.95, "відмова (секрет без прав)", MUTED, dashed=True)
    msg(4, 3, 1.45, "4. опитування журналів\nщохвилини", BLUE)
    msg(3, 4, 1.05, "запис: час t₁, IP,\nназва виклику", BLUE, dashed=True)
    box(ax, xs[4] - hw / 2, 0.42, hw, 0.5, "5. TTFU = t₁ − t₀\nзапис у SQLite", ec=AQUA, fc="#effaf5", fs=FS_S)
    ax.text(0.04, 0.2, "Паралельно платформа може сама нейтралізувати секрет (GitHub secret scanning → "
            "карантин AWS,\nвимкнення ключа Google). Ці події записуються окремо як exposed і не входять у TTFU.",
            fontsize=FS_S, color=MUTED, style="italic", va="center",
            bbox=dict(boxstyle="square,pad=0.1", fc="white", ec="none"))
    save(fig, OUT / "fig-03-01-detectors.png", pct)


def fig_llmjacking(pct=100):
    # Кількості — з raw-cloud-events.jsonl знімка 20261120T1340Z: лише виклики інструмента, що першим
    # використав чотири ключі з paste-сервісу (одна IP-адреса, 19.10 20:15:09–20:15:31 UTC, 22 с).
    # Виклики інших інструментів (огляд 15 регіонів, GetServiceQuota, Converse) сюди не додаються.
    steps = [("Перевірка ключа", "GetCallerIdentity", "4 виклики"),
             ("Пошук моделей", "ListFoundationModels", "8 викликів, 2 регіони"),
             ("Доступність моделей", "GetFoundationModelAvailability", "316 викликів, 6 регіонів"),
             ("Спроба відкрити доступ", "PutUseCaseForModelAccess", "4 виклики"),
             ("Виклик моделі", "InvokeModel", "160 викликів, 6 регіонів")]
    W = width_in(pct)
    bh, gap = 0.44, 0.17
    H = len(steps) * (bh + gap) + 0.45
    fig, ax = canvas(W, H)
    bw = 5.9
    x0 = (W - bw) / 2
    for i, (h, api, cnt) in enumerate(steps):
        y = H - 0.04 - (i + 1) * bh - i * gap
        last = i == len(steps) - 1
        box(ax, x0, y, bw, bh, ec=RED if last else INK, lw=1.5 if last else 1.1)
        ax.text(x0 + 0.15, y + bh / 2, f"{i + 1}. {h}", va="center", fontsize=FS, fontweight="bold")
        ax.plot([x0 + 1.95, x0 + 1.95], [y + 0.07, y + bh - 0.07], color="#d0d0d0", lw=0.8)
        ax.text(x0 + 2.08, y + bh / 2, api, va="center", fontsize=FS, color=INK)
        if cnt:
            ax.text(x0 + bw - 0.15, y + bh / 2, cnt, va="center", ha="right", fontsize=FS, color=MUTED)
        if i:
            arrow(ax, W / 2, y + bh + gap, W / 2, y + bh)
    ax.text(x0, 0.22, "Паралельно: розвідка витрат і прав (GetCostAndUsage — 8, ListAttachedUserPolicies — 4).\n"
            "Усі виклики відхилено: ключі без прав, витрат немає.", fontsize=FS_S, color=MUTED, style="italic",
            va="center")
    save(fig, OUT / "fig-04-03-llmjacking.png", pct)


# ----------------------------------------------------------------------------- дані кампанії (розділ 4)

LABEL = {"github": "GitHub", "dotenv": ".env у репозиторії", "paste": "paste-сервіс", "ci-log": "журнал CI/CD"}
ORDER = {"github": 0, "dotenv": 1, "paste": 2, "ci-log": 3}


def snap_date(snap: Path) -> datetime:
    try:
        return datetime.strptime(snap.name, "%Y%m%dT%H%MZ")
    except ValueError:  # каталог без мітки часу (напр. data/sample) — дата зміни файлу
        return datetime.fromtimestamp((snap / "ttc.csv").stat().st_mtime)


def read_campaign_csv(snap: Path) -> pd.DataFrame:
    """ttc-campaign.csv зі знімка; якщо його немає (синтетичний знімок) — ttc.csv."""
    path = snap / "ttc-campaign.csv"
    return pd.read_csv(path if path.exists() else snap / "ttc.csv")


def campaign(snap: Path) -> pd.DataFrame:
    df = read_campaign_csv(snap)
    return df.assign(o=df.channel.map(ORDER)).sort_values(["o", "visibility", "token_id"])


def timeline(snap, secret_type, fname, slow_after_s, slow_label, xmax_days=36, waves=(), pct=95):
    df = campaign(snap)
    df = df[df.secret_type == secret_type].reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(width_in(pct) - 0.35, 3.6))
    n = len(df)
    for i, r in df.iterrows():
        y = n - 1 - i
        ax.plot([5, r.ttc_seconds], [y, y], color="#d0d0d0", lw=0.9, zorder=0)
        if r.exposed_seconds == r.exposed_seconds:
            ax.scatter(r.exposed_seconds, y, marker="v", s=22, color=MUTED, zorder=2)
        if r.censored:
            ax.scatter(r.ttc_seconds, y, marker="|", s=50, color=MUTED, zorder=2)
        else:
            ax.scatter(r.ttc_seconds, y, s=26, color=RED if r.ttc_seconds > slow_after_s else BLUE, zorder=3)
    for ch, g in df.groupby("channel"):
        ys = [n - 1 - i for i in g.index]
        ax.text(3.6, (min(ys) + max(ys)) / 2, LABEL[ch], ha="right", va="center", fontsize=FS)
        ax.axhline(min(ys) - 0.5, color="#ececec", lw=0.8)
    ax.set_xscale("log")
    ax.set_xlim(5, xmax_days * DAY)
    ax.set_ylim(-0.7, n + 0.3)
    ticks = [10, 60, 600, 3600, 6 * 3600, DAY, 7 * DAY, 30 * DAY]
    ax.set_xticks(ticks, ["10 с", "1 хв", "10 хв", "1 год", "6 год", "1 доба", "7 діб", "30 діб"])
    ax.minorticks_off()
    ax.set_yticks([])
    for lo, hi, txt in waves:
        ax.axvspan(lo * DAY, hi * DAY, color=RED, alpha=0.06)
        ax.text((lo * hi) ** 0.5 * DAY, n - 0.35, txt, ha="center", fontsize=FS_S, color=RED)
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.set_xlabel("Час від публікації (логарифмічна шкала)")
    h = [plt.Line2D([], [], marker="o", ls="", color=BLUE, label="перше використання"),
         plt.Line2D([], [], marker="o", ls="", color=RED, label=slow_label),
         plt.Line2D([], [], marker="|", ls="", color=MUTED, markersize=9,
                    label=f"не використано (на {snap_date(snap):%d.%m})")]
    if df.exposed_seconds.notna().any():
        h.insert(0, plt.Line2D([], [], marker="v", ls="", color=MUTED, label="нейтралізовано платформою"))
    ax.legend(handles=h, loc="upper center", bbox_to_anchor=(0.4, -0.13), ncol=2, frameon=False,
              columnspacing=1.2, handletextpad=0.3)
    save(fig, OUT / fname, pct)


def _axes_common(ax):
    ax.grid(True, color="#e6e6e6", lw=0.6)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


def fig_interim(snap, pct=90):
    """Як analysis.interim_report.plot, без заголовка."""
    from lifelines import KaplanMeierFitter
    from analysis.analyze_campaign import COLORS, UA, fmt_dur
    from analysis.interim_report import CHANNELS, STYLES, load
    df = load(snap)
    fig, ax = plt.subplots(figsize=(width_in(pct) + 0.15, 3.0))
    for ch in CHANNELS:
        sub = df[df.channel == ch]
        kmf = KaplanMeierFitter().fit(sub.ttc_seconds, sub.event)
        cdf = 1 - kmf.survival_function_.iloc[:, 0]
        t_end = float(sub.ttc_seconds.min() if sub.event.sum() == 0 else sub.ttc_seconds.max())
        cdf = cdf[cdf.index <= t_end]
        xs = [10.0] + [max(float(t), 10.0) for t in cdf.index[1:]] + [t_end]
        ys = [0.0] + list(cdf.values[1:]) + [float(cdf.values[-1])]
        ax.step(xs, ys, where="post", color=COLORS[ch], ls=STYLES[ch], lw=1.8,
                label=f"{UA[ch]} ({int(sub.event.sum())}/{len(sub)})")
    first = df[df.event == 1].ttc_seconds.min()
    ax.annotate(f"перше використання:\n{fmt_dur(first)} після публікації", (first, 1 / 24),
                xytext=(420, 0.11), textcoords="data", fontsize=FS_S, color="#52514e", va="center",
                arrowprops=dict(arrowstyle="-", color="#9a9a96", lw=0.8))
    ax.set_xscale("log")
    ax.set_xlim(10, 36 * DAY)
    ax.set_xticks([60, 900, 3600, 6 * 3600, DAY, 7 * DAY, 30 * DAY])
    ax.set_xticklabels(["1 хв", "15 хв", "1 год", "6 год", "1 доба", "7 діб", "30 діб"])
    ax.minorticks_off()
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0%}".replace(".", ",")))
    ax.set_ylim(0, 0.55)
    ax.set_xlabel("Час після публікації (логарифмічна шкала)")
    ax.set_ylabel("Частка використаних токенів")
    _axes_common(ax)
    ax.grid(False, axis="x")
    ax.legend(frameon=False, loc="upper left", title="Канал (використано/опубліковано)", title_fontsize=FS_S)
    save(fig, OUT / "fig-interim-channel.png", pct)


def fig_km(snap, col, levels, fname, pct=90):
    """Як analysis.analyze_campaign.plot_km, без заголовка."""
    from lifelines import KaplanMeierFitter
    from analysis.analyze_campaign import COLORS, STYLES, UA
    df = read_campaign_csv(snap)
    df["event"] = 1 - df["censored"].astype(int)
    df["ttc_seconds"] = df["ttc_seconds"].clip(lower=1e-3)
    fig, ax = plt.subplots(figsize=(width_in(pct) + 0.15, 3.0))
    for i, lv in enumerate(levels):
        sub = df[df[col] == lv]
        if sub.empty:
            continue
        kmf = KaplanMeierFitter().fit(sub.ttc_seconds, sub.event, label=UA.get(lv, lv))
        kmf.plot_survival_function(ax=ax, ci_show=False, color=COLORS.get(lv), ls=STYLES[i % 4], lw=1.8)
    ax.set_xscale("log")
    ax.set_xlim(10, 40 * DAY)
    ax.set_xticks([60, 3600, DAY, 7 * DAY, 30 * DAY])
    ax.set_xticklabels(["1 хв", "1 год", "1 доба", "7 діб", "30 діб"])
    ax.minorticks_off()
    ax.yaxis.set_major_formatter(COMMA1)
    ax.set_ylim(0, 1.02)
    ax.set_xlabel("Час після публікації (логарифмічна шкала)")
    ax.set_ylabel("Частка ще не використаних\nтокенів S(t)")
    _axes_common(ax)
    ax.legend(frameon=False, loc="lower left")
    save(fig, OUT / fname, pct)


def fig_risk(snap, impact=0.8, pct=90):
    """Як analysis.analyze_campaign.plot_risk (I = 0,8 — значення за замовчуванням у analyze()), без заголовка."""
    from analysis.analyze_campaign import COLORS, STYLES, UA
    from modeling.risk import prob_compromise_within
    from modeling.survival import fit_best_distribution
    df = read_campaign_csv(snap)
    df["event"] = 1 - df["censored"].astype(int)
    df["ttc_seconds"] = df["ttc_seconds"].clip(lower=1e-3)
    fits = {ch: fit_best_distribution(g.ttc_seconds.to_numpy(), g.event.to_numpy())
            for ch, g in df.groupby("channel") if g.event.sum() > 0}
    t = np.logspace(0, math.log10(30 * DAY), 300)
    fig, ax = plt.subplots(figsize=(width_in(pct) + 0.15, 3.0))
    for i, (ch, fit) in enumerate(fits.items()):
        ax.plot(t, [prob_compromise_within(fit.name, fit.params, x) * impact for x in t],
                color=COLORS.get(ch), ls=STYLES[i % 4], lw=1.8, label=UA.get(ch, ch))
    ax.axvline(60, color=MUTED, lw=0.8, ls=":")
    ax.text(68, 0.77, "TTL = 60 с", fontsize=FS_S, color=MUTED)
    ax.set_xscale("log")
    ax.set_xticks([1, 60, 3600, DAY, 30 * DAY])
    ax.set_xticklabels(["1 с", "1 хв", "1 год", "1 доба", "30 діб"])
    ax.minorticks_off()
    ax.yaxis.set_major_formatter(COMMA1)
    ax.set_ylim(0, 0.82)
    ax.set_xlabel("Термін дії облікових даних TTL (логарифмічна шкала)")
    ax.set_ylabel(f"Залишковий ризик F(TTL) · I,\nI = {impact}".replace(".", ","))
    _axes_common(ax)
    ax.legend(frameon=False, loc="upper left")
    save(fig, OUT / "fig-risk-ttl.png", pct)


def crop_ttl_screenshot() -> None:
    """Рис. 3.1: реальний скриншот стенду (text/figures/stand/) без змін вмісту — лише обрізано порожнє
    поле під виводом, щоб при width=100% текст був якомога більшим (ширину обмежує рядок kubectl)."""
    from PIL import Image
    src = ROOT / "text/figures/stand/fig-09-02-ttl-connect-expired.png"
    dst = OUT / "stand/fig-09-02-ttl-connect-expired.png"
    if not src.exists():  # скриншот стенду в цей репозиторій не входить (див. stand/)
        print(f"пропущено: немає {src.relative_to(ROOT)}")
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    Image.open(src).crop((0, 0, 1200, 288)).save(dst)
    print(f"{dst.relative_to(ROOT)}: обрізано з {src.relative_to(ROOT)}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("snapshot", nargs="?", type=Path, default=DEFAULT_SNAP,
                    help="каталог знімка кампанії (data/campaign/<YYYYMMDDTHHMMZ>)")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    snap = a.snapshot.resolve()
    print(f"знімок: {snap.name}")
    fig_architecture(); fig_measurement(); fig_weibull(); fig_attack_tree()
    fig_detectors(); fig_llmjacking(); crop_ttl_screenshot()
    timeline(snap, "aws", "fig-04-04-aws-wave.png", 4 * DAY, "перше використання у хвилі 26.10",
             waves=[(5.3, 7.3, "хвиля 26.10")])
    timeline(snap, "db", "fig-04-06-db-timeline.png", 10 * DAY, "відкладене використання (03–09.11)",
             waves=[(14.0, 21.5, "03–09.11")])
    fig_interim(snap)
    fig_km(snap, "channel", ["github", "dotenv", "ci-log", "paste"], "fig-km-channel.png")
    fig_km(snap, "secret_type", ["aws", "gcp", "api", "db"], "fig-km-type.png")
    fig_risk(snap)
    print("ok")


if __name__ == "__main__":
    main()
