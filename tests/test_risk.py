import numpy as np
from modeling.risk import (prob_compromise_within, residual_risk,
                           expert_baseline_risk, monte_carlo_residual_risk)


def test_prob_compromise_within_weibull_matches_analytic():
    # S(t)=exp(-(t/lam)^rho); F(t)=1-S(t)
    lam, rho, ttl = 3600.0, 1.0, 3600.0
    expected = 1 - np.exp(-(ttl / lam) ** rho)  # = 1 - e^-1 ≈ 0.632
    got = prob_compromise_within("weibull", {"lambda": lam, "rho": rho}, ttl)
    assert abs(got - expected) < 1e-9


def test_prob_increases_with_ttl():
    p_short = prob_compromise_within("weibull", {"lambda": 3600.0, "rho": 1.2}, 60.0)
    p_long = prob_compromise_within("weibull", {"lambda": 3600.0, "rho": 1.2}, 86400.0)
    assert p_short < p_long
    assert p_long > 0.99


def test_residual_risk_scales_with_impact():
    r = residual_risk("weibull", {"lambda": 3600.0, "rho": 1.0}, ttl=3600.0, impact=0.8)
    p = 1 - np.exp(-1)
    assert abs(r - p * 0.8) < 1e-9


def test_expert_baseline_matches_coursework_number():
    # відтворення курсової: середній зважений ризик "before"
    threats = [
        {"prob": 0.8, "impact": 0.8},
        {"prob": 0.5, "impact": 0.8},
        {"prob": 0.95, "impact": 0.8},
    ]
    avg = expert_baseline_risk(threats)
    assert abs(avg - np.mean([0.64, 0.40, 0.76])) < 1e-9


def test_monte_carlo_returns_ordered_ci():
    result = monte_carlo_residual_risk(
        "weibull", {"lambda": 3600.0, "rho": 1.0}, ttl=3600.0, impact=1.0,
        n=1000, seed=0)
    assert result["ci_low"] <= result["median"] <= result["ci_high"]
    assert abs(result["median"] - (1 - np.exp(-1))) < 0.05


def test_bootstrap_ci_ordered_and_brackets_point_estimate():
    from synthetic import sample_weibull_ttc
    from modeling.risk import bootstrap_residual_risk_ci
    d, e = sample_weibull_ttc(n=400, lam=3600.0, rho=1.2, seed=1)
    ci = bootstrap_residual_risk_ci(d, e, [3600.0], impact=1.0, n_boot=80, seed=0)["3600.0"]
    assert ci["ci_low"] <= ci["median"] <= ci["ci_high"]
    point = residual_risk("weibull", {"lambda": 3600.0, "rho": 1.2}, 3600.0, 1.0)
    assert ci["ci_low"] <= point <= ci["ci_high"]
