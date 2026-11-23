import csv
import numpy as np
from deploy.simulate_campaign import run, generate_decoy


def test_run_produces_wellformed_csv_and_manifest(tmp_path):
    s = run(tmp_path / "ttc.csv", tmp_path / "man.csv", tmp_path / "sim.db",
            replicas=2, seed=1)
    assert s["tokens"] == 4 * 4 * 2 * 2  # channels * secret_types * visibilities * replicas
    assert s["observed"] + s["censored"] == s["tokens"]

    rows = list(csv.DictReader(open(tmp_path / "ttc.csv", encoding="utf-8")))
    assert len(rows) == 64
    assert set(rows[0]) == {"token_id", "secret_type", "channel", "visibility",
                            "ttc_seconds", "censored", "time_precise", "exposed_seconds"}

    man = list(csv.DictReader(open(tmp_path / "man.csv", encoding="utf-8")))
    assert len(man) == 64
    assert all(r["decoy_value"] for r in man)


def test_decoy_formats_are_recognizable():
    rng = np.random.default_rng(0)
    assert generate_decoy("aws", rng).startswith("AKIA")
    assert generate_decoy("db", rng).startswith("postgresql://")
    assert generate_decoy("api", rng).startswith("tok_")


def test_run_is_deterministic_with_seed(tmp_path):
    run(tmp_path / "a.csv", tmp_path / "am.csv", tmp_path / "a.db", replicas=2, seed=5)
    run(tmp_path / "b.csv", tmp_path / "bm.csv", tmp_path / "b.db", replicas=2, seed=5)
    a = (tmp_path / "a.csv").read_text(encoding="utf-8")
    b = (tmp_path / "b.csv").read_text(encoding="utf-8")
    assert a == b
