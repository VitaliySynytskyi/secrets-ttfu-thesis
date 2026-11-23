from __future__ import annotations
import numpy as np
from scipy.stats import norm
from .survival import fit_best_distribution

POSITIVE_ONLY = {"lambda", "rho", "sigma", "cure"}  # mu is signed


def _survival(name: str, params: dict, t: float) -> float:
    if t <= 0:
        return 1.0  # S(0)=1
    if name == "weibull":
        return float(np.exp(-(t / params["lambda"]) ** params["rho"]))
    if name == "exponential":
        return float(np.exp(-t / params["lambda"]))
    if name == "lognormal":
        return float(1 - norm.cdf((np.log(t) - params["mu"]) / params["sigma"]))
    if name == "lognormal_cure":
        s_ln = 1 - norm.cdf((np.log(t) - params["mu"]) / params["sigma"])
        return float(params["cure"] + (1 - params["cure"]) * s_ln)
    raise ValueError(f"unknown distribution: {name}")


def prob_compromise_within(name: str, params: dict, ttl: float) -> float:
    """F(TTL) = P(компрометація <= TTL) = 1 - S(TTL)."""
    return 1.0 - _survival(name, params, ttl)


def residual_risk(name: str, params: dict, ttl: float, impact: float) -> float:
    """Залишковий ризик = P(компрометація <= TTL) * impact."""
    return prob_compromise_within(name, params, ttl) * impact


def expert_baseline_risk(threats: list[dict]) -> float:
    """Середній зважений ризик за експертними prob*impact (baseline курсової)."""
    return float(np.mean([t["prob"] * t["impact"] for t in threats]))


def monte_carlo_residual_risk(name: str, params: dict, ttl: float, impact: float,
                              n: int = 10000, rel_sigma: float = 0.1,
                              seed: int = 0) -> dict:
    """Parameter-sensitivity band (fixed rel_sigma), NOT a statistical confidence interval.
    For a data-driven CI use bootstrap_residual_risk_ci."""
    rng = np.random.default_rng(seed)
    samples = []
    for _ in range(n):
        noisy = {k: v * (1 + rng.normal(0, rel_sigma)) for k, v in params.items()}
        noisy = {k: max(v, 1e-6) if k in POSITIVE_ONLY else v for k, v in noisy.items()}
        if "cure" in noisy:
            noisy["cure"] = min(noisy["cure"], 0.999)
        samples.append(residual_risk(name, noisy, ttl, impact))
    arr = np.array(samples)
    return {"median": float(np.median(arr)),
            "ci_low": float(np.percentile(arr, 2.5)),
            "ci_high": float(np.percentile(arr, 97.5))}


def bootstrap_residual_risk_ci(durations, events, ttls, impact, n_boot=400, seed=0):
    """Bootstrap CI for residual risk at each TTL: resample the TTC sample with
    replacement, refit the best distribution, recompute residual risk. Returns
    {str(ttl): {"median":.., "ci_low":.., "ci_high":..}} (2.5/97.5 percentiles)."""
    durations = np.asarray(durations, dtype=float)
    events = np.asarray(events, dtype=int)
    rng = np.random.default_rng(seed)
    n = len(durations)
    if n == 0:
        raise ValueError("empty sample")
    collected = {str(t): [] for t in ttls}
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        fit = fit_best_distribution(durations[idx], events[idx])
        for t in ttls:
            collected[str(t)].append(residual_risk(fit.name, fit.params, float(t), impact))
    out = {}
    for t in ttls:
        arr = np.array(collected[str(t)])
        out[str(t)] = {"median": float(np.median(arr)),
                       "ci_low": float(np.percentile(arr, 2.5)),
                       "ci_high": float(np.percentile(arr, 97.5))}
    return out
