import numpy as np
from synthetic import sample_weibull_ttc


def test_sample_shape_and_positivity():
    durations, events = sample_weibull_ttc(n=500, lam=3600.0, rho=1.2, seed=42)
    assert len(durations) == 500
    assert len(events) == 500
    assert np.all(durations > 0)
    assert set(np.unique(events)).issubset({0, 1})


def test_seed_is_deterministic():
    a = sample_weibull_ttc(n=100, lam=3600.0, rho=1.2, seed=7)[0]
    b = sample_weibull_ttc(n=100, lam=3600.0, rho=1.2, seed=7)[0]
    assert np.allclose(a, b)


def test_censoring_caps_durations():
    t, ev = sample_weibull_ttc(n=500, lam=3600.0, rho=1.0, seed=5, censor_at=1800.0)
    assert np.all(t <= 1800.0)
    assert np.any(ev == 0)
