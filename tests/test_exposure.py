# diploma/experiment/tests/test_exposure.py
from modeling.exposure import exposure_window_seconds


def test_exposure_window_from_lease_and_revoke():
    audit = [
        {"time": "2026-08-01T10:00:00Z", "type": "lease", "lease_id": "db/creds/x"},
        {"time": "2026-08-01T10:01:00Z", "type": "revoke", "lease_id": "db/creds/x"},
    ]
    assert exposure_window_seconds(audit, "db/creds/x") == 60.0


def test_predicted_risk_at_exposure_matches_residual_risk():
    from modeling.exposure import predicted_risk_at_exposure
    from modeling.risk import residual_risk
    val = predicted_risk_at_exposure(60.0, "weibull", {"lambda": 3600.0, "rho": 1.0}, 0.8)
    assert abs(val - residual_risk("weibull", {"lambda": 3600.0, "rho": 1.0}, 60.0, 0.8)) < 1e-12
