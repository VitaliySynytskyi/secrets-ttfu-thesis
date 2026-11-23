from synthetic import sample_weibull_ttc
from modeling.survival import km_survival, fit_best_distribution


def test_km_survival_is_monotone_decreasing():
    durations, events = sample_weibull_ttc(n=400, lam=3600.0, rho=1.3, seed=1)
    times, surv = km_survival(durations, events)
    assert surv[0] <= 1.0
    assert all(surv[i] >= surv[i + 1] - 1e-9 for i in range(len(surv) - 1))


def test_fit_recovers_known_weibull_params():
    durations, events = sample_weibull_ttc(n=4000, lam=3600.0, rho=1.3, seed=2)
    fit = fit_best_distribution(durations, events)
    assert fit.name == "weibull"
    # відновлення параметрів у межах 12%
    assert abs(fit.params["lambda"] - 3600.0) / 3600.0 < 0.12
    assert abs(fit.params["rho"] - 1.3) / 1.3 < 0.12


def test_fit_returns_aic_for_all_candidates():
    durations, events = sample_weibull_ttc(n=1000, lam=1800.0, rho=1.0, seed=3)
    fit = fit_best_distribution(durations, events)
    assert {"weibull", "exponential", "lognormal"}.issubset(fit.all_aic.keys())


def test_cure_model_selected_when_many_never_used():
    # 40 % токенів не використано за 30 діб (плато), решта: логнормальний час ~10 хв
    import numpy as np
    from modeling.survival import fit_best_distribution
    from modeling.risk import prob_compromise_within
    rng = np.random.default_rng(7)
    n = 200
    used = rng.random(n) < 0.6
    t = np.where(used, rng.lognormal(np.log(600), 1.0, n), 30 * 86400.0)
    fit = fit_best_distribution(t, used.astype(int))
    assert fit.name == "lognormal_cure"
    assert 0.3 < fit.params["cure"] < 0.5
    # на дуже довгому горизонті F не перевищує частку тих, кого взагалі використали
    assert prob_compromise_within(fit.name, fit.params, 1e9) < 0.7
