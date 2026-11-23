# diploma/experiment/calculator/curve.py
from __future__ import annotations
from pathlib import Path
import matplotlib
if matplotlib.get_backend().lower() != "agg":
    matplotlib.use("Agg")
import matplotlib.pyplot as plt
from modeling.risk import residual_risk


def risk_curve(name: str, params: dict, ttls, impact: float) -> list[float]:
    return [residual_risk(name, params, float(ttl), impact) for ttl in ttls]


def save_risk_curve_png(name: str, params: dict, ttls, impact: float,
                        out_path: Path | str) -> None:
    risks = risk_curve(name, params, ttls, impact)
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(ttls, risks, marker="o")
    ax.set_xscale("log")
    ax.set_xlabel("TTL секрету, с (лог. шкала)")
    ax.set_ylabel("Залишковий ризик")
    ax.set_title("Залежність залишкового ризику від TTL")
    ax.grid(True, which="both", alpha=0.3)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
