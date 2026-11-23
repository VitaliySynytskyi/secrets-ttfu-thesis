from __future__ import annotations
from dataclasses import dataclass
import warnings
from lifelines import (KaplanMeierFitter, WeibullFitter,
                       ExponentialFitter, LogNormalFitter, MixtureCureFitter)


@dataclass
class DistFit:
    name: str
    params: dict
    aic: float
    all_aic: dict


def km_survival(durations, events):
    """Повертає (times, survival) за оцінкою Каплана–Меєра."""
    kmf = KaplanMeierFitter()
    kmf.fit(durations, event_observed=events)
    sf = kmf.survival_function_
    times = sf.index.to_numpy(dtype=float)
    surv = sf.iloc[:, 0].to_numpy(dtype=float)
    return times, surv


def fit_best_distribution(durations, events) -> DistFit:
    """Підігнати кандидатні розподіли, обрати найкращий за AIC."""
    candidates = {}
    wf = WeibullFitter().fit(durations, event_observed=events)
    candidates["weibull"] = (wf.AIC_, {"lambda": float(wf.lambda_), "rho": float(wf.rho_)})

    ef = ExponentialFitter().fit(durations, event_observed=events)
    candidates["exponential"] = (ef.AIC_, {"lambda": float(ef.lambda_)})

    lnf = LogNormalFitter().fit(durations, event_observed=events)
    candidates["lognormal"] = (lnf.AIC_, {"mu": float(lnf.mu_), "sigma": float(lnf.sigma_)})

    # Модель зі стійкою часткою (cure model): частина секретів не використовується ніколи,
    # S(t) = cure + (1 - cure) * S_lognormal(t). Без неї F(TTL) на довгих TTL завищується.
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            cf = MixtureCureFitter(base_fitter=LogNormalFitter()).fit(durations, event_observed=events)
        candidates["lognormal_cure"] = (cf.AIC_, {"mu": float(cf.mu_), "sigma": float(cf.sigma_),
                                                  "cure": float(cf.cured_fraction_)})
    except Exception:  # на вироджених вибірках (без цензурування) підгонка може не зійтися
        pass

    all_aic = {k: v[0] for k, v in candidates.items()}
    best = min(candidates, key=lambda k: candidates[k][0])
    return DistFit(name=best, params=candidates[best][1],
                   aic=candidates[best][0], all_aic=all_aic)
