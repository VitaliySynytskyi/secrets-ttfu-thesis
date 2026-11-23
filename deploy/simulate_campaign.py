#!/usr/bin/env python3
"""Dry-run of the first-party honeytoken campaign with RANDOMLY GENERATED decoys.

This SIMULATES the campaign end-to-end through the REAL collector code path
(register -> record_hit -> export) so you can see exactly how to reproduce it,
WITHOUT publishing anything publicly. It:
  1. generates a random, NON-FUNCTIONAL decoy value per token (written to a manifest),
  2. registers the deployment plan in a TtcStore,
  3. simulates first-use ("compromise") events by drawing TTC from the per-channel
     calibrated distributions (provenance: docs/ttc-sources.md),
  4. exports a ttc.csv identical in shape to a real collected dataset.

TO RUN A REAL CAMPAIGN instead (see deploy/README.md):
  - replace each decoy with a real Canarytoken (alerts on use, grants NO access),
  - publish each to its channel at a recorded time (= published_at),
  - run the FastAPI collector (collector.app) behind a public URL and let real
    scanner hits arrive via webhook; skip the simulate step entirely.
The downstream pipeline (calculator.cli) consumes the resulting ttc.csv unchanged.
"""
from __future__ import annotations
import argparse
import csv
import math
import string
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from collector.model import Honeytoken, Hit  # noqa: E402
from collector.store import TtcStore  # noqa: E402
from collector.registry import build_plan  # noqa: E402

# Per-channel TTC calibration (literature-based prior).
# Provenance & citations: docs/ttc-sources.md.
CHANNEL_TTC = {
    "github": {"median_s": 5 * 60,         "sigma": 1.0, "exploit": 0.91},
    "dotenv": {"median_s": 5 * 60,         "sigma": 1.0, "exploit": 0.91},
    "ci-log": {"median_s": 7 * 60,         "sigma": 1.2, "exploit": 0.70},
    "paste":  {"median_s": int(6.2 * 3600), "sigma": 1.2, "exploit": 0.50},
}
SECRET_TYPE_MULT = {"aws": 1.0, "gcp": 1.5, "api": 2.0, "db": 3.0}
HORIZON_S = 30 * 24 * 3600
BASE_PUBLISHED = datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)


def _rand(rng, n: int, alphabet: str) -> str:
    idx = rng.integers(0, len(alphabet), size=n)
    return "".join(alphabet[i] for i in idx)


def generate_decoy(secret_type: str, rng) -> str:
    """A RANDOM, non-functional decoy value. A real campaign uses Canarytokens."""
    upper_digits = string.ascii_uppercase + string.digits
    b64 = string.ascii_letters + string.digits
    if secret_type == "aws":
        return f"AKIA{_rand(rng, 16, upper_digits)}:{_rand(rng, 40, b64)}"
    if secret_type == "gcp":
        return "AIza" + _rand(rng, 35, string.ascii_letters + string.digits + "-_")
    if secret_type == "db":
        return (f"postgresql://app_{_rand(rng, 6, string.ascii_lowercase)}:"
                f"{_rand(rng, 18, b64)}@db.internal:5432/appdb")
    if secret_type == "api":
        return "tok_" + _rand(rng, 32, string.hexdigits[:16])
    return _rand(rng, 24, b64)


def run(out_csv, manifest_csv, db_path, replicas: int = 3, seed: int = 20260627,
        base_published: datetime = BASE_PUBLISHED) -> dict:
    """Simulate a campaign through the real collector path and export ttc.csv + manifest."""
    if Path(db_path).exists():
        Path(db_path).unlink()  # fresh campaign -> deterministic for a given seed
    rng = np.random.default_rng(seed)
    store = TtcStore(db_path)
    plan = build_plan(replicas=replicas, published_at=base_published)
    manifest: list[dict] = []
    observed = 0
    for tok in plan:
        store.register(tok)
        manifest.append({
            "token_id": tok.token_id, "channel": tok.channel,
            "secret_type": tok.secret_type, "visibility": tok.visibility,
            "decoy_value": generate_decoy(tok.secret_type, rng),
        })
        cfg = CHANNEL_TTC[tok.channel]
        mu = math.log(cfg["median_s"] * SECRET_TYPE_MULT[tok.secret_type])
        if rng.random() < cfg["exploit"]:
            ttc = float(rng.lognormal(mean=mu, sigma=cfg["sigma"]))
            if ttc < HORIZON_S:
                used_at = base_published + timedelta(seconds=ttc)
                ip = ".".join(str(int(rng.integers(1, 255))) for _ in range(4))
                store.record_hit(Hit(tok.token_id, used_at, ip))
                observed += 1
    store.export_csv(out_csv, now=base_published + timedelta(seconds=HORIZON_S))
    Path(manifest_csv).parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["token_id", "channel", "secret_type",
                                           "visibility", "decoy_value"])
        w.writeheader()
        w.writerows(manifest)
    return {"tokens": len(plan), "observed": observed, "censored": len(plan) - observed,
            "out_csv": str(out_csv), "manifest": str(manifest_csv)}


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    data = Path(__file__).resolve().parents[1] / "data"
    p = argparse.ArgumentParser(description="Honeytoken campaign dry-run (random decoys).")
    p.add_argument("--replicas", type=int, default=3)
    p.add_argument("--seed", type=int, default=20260627)
    p.add_argument("--out", default=str(data / "ttc-simulated.csv"))
    p.add_argument("--manifest", default=str(data / "campaign-manifest.csv"))
    p.add_argument("--db", default=str(data / "ttc-sim.db"))
    a = p.parse_args()
    s = run(a.out, a.manifest, a.db, replicas=a.replicas, seed=a.seed)
    print(f"Simulated {s['tokens']} honeytokens "
          f"({s['observed']} compromised, {s['censored']} censored).")
    print(f"  TTC dataset:    {s['out_csv']}")
    print(f"  Decoy manifest: {s['manifest']}")
    print("\nThis is a SIMULATION with random decoys. For a real campaign (deploy/README.md):")
    print("  publish each manifest decoy (ideally a Canarytoken) to its channel,")
    print("  run the collector webhook, and let real scanner hits populate the dataset.")
    print("Then: calculator.cli <ttc.csv> --ttl 15 --ttl 60 --ttl 300 --ttl 3600 ...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
