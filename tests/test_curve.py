# diploma/experiment/tests/test_curve.py
from calculator.curve import risk_curve, save_risk_curve_png


def test_risk_curve_monotone_increasing_in_ttl():
    ttls = [15, 60, 300, 3600, 86400]
    risks = risk_curve("weibull", {"lambda": 3600.0, "rho": 1.2}, ttls, impact=0.8)
    assert len(risks) == len(ttls)
    assert all(risks[i] <= risks[i + 1] + 1e-9 for i in range(len(risks) - 1))


def test_risk_curve_png_written(tmp_path):
    out = tmp_path / "fig.png"
    save_risk_curve_png("weibull", {"lambda": 3600.0, "rho": 1.2},
                        [15, 60, 300, 3600, 86400], impact=0.8, out_path=out)
    assert out.exists() and out.stat().st_size > 0
