from __future__ import annotations
import numpy as np


def sample_weibull_ttc(n: int, lam: float, rho: float, seed: int,
                       censor_at: float | None = None):
    """Згенерувати n TTC-спостережень із розподілу Вейбулла S(t)=exp(-(t/lam)^rho).

    Повертає (durations, events): events=1 — спостережено, 0 — цензуровано.
    """
    rng = np.random.default_rng(seed)
    # lifelines-параметризація: t = lam * (-ln U)^(1/rho)
    u = rng.uniform(size=n)
    t = lam * (-np.log(u)) ** (1.0 / rho)
    events = np.ones(n, dtype=int)
    if censor_at is not None:
        events = (t <= censor_at).astype(int)
        t = np.minimum(t, censor_at)
    return t, events
