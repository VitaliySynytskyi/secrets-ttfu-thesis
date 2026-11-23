# diploma/experiment/modeling/exposure.py
from __future__ import annotations
from datetime import datetime


def exposure_window_seconds(audit_events: list[dict], lease_id: str) -> float:
    """Час між видачею lease і його відкликанням (спостережене вікно експозиції)."""
    t_lease = t_revoke = None
    for ev in audit_events:
        if ev.get("lease_id") != lease_id:
            continue
        t = datetime.fromisoformat(ev["time"].replace("Z", "+00:00"))
        if ev["type"] == "lease":
            t_lease = t
        elif ev["type"] == "revoke":
            t_revoke = t
    if t_lease is None or t_revoke is None:
        raise ValueError("lease/revoke не знайдено")
    return (t_revoke - t_lease).total_seconds()


def predicted_risk_at_exposure(window_seconds, name, params, impact):
    """Model's residual risk if the secret were exposed for the OBSERVED window
    (bridges stand-observed lease->revoke window to the calibrated F(TTL))."""
    from .risk import residual_risk
    return residual_risk(name, params, float(window_seconds), impact)
