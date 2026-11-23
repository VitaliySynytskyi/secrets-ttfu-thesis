# diploma/experiment/deploy/seed.py
from __future__ import annotations
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from collector.registry import build_plan, CHANNELS, SECRET_TYPES, VISIBILITIES
from collector.model import Honeytoken
from collector.store import TtcStore


def main() -> int:
    p = argparse.ArgumentParser(
        description="Зареєструвати план honeytoken-кампанії (повний або звужений пілотний зріз)."
    )
    p.add_argument("--channels", nargs="+", default=list(CHANNELS), choices=CHANNELS)
    p.add_argument("--secret-types", nargs="+", default=list(SECRET_TYPES), choices=SECRET_TYPES)
    p.add_argument("--visibilities", nargs="+", default=list(VISIBILITIES), choices=VISIBILITIES)
    p.add_argument("--replicas", type=int, default=3)
    p.add_argument("--replica-start", type=int, default=0,
                   help="перша репліка (основна кампанія: 1, бо 0 зайняв пілот)")
    p.add_argument("--calib", action="store_true",
                   help="також зареєструвати calib-<тип>-0 (канал calib) для наскрізної перевірки")
    args = p.parse_args()

    store = TtcStore(Path(__file__).resolve().parents[1] / "data" / "ttc.db")
    plan = build_plan(replicas=args.replicas, channels=args.channels,
                       secret_types=args.secret_types, visibilities=args.visibilities,
                      replica_start=args.replica_start)
    if args.calib:
        plan += [Honeytoken(f"calib-{t}-0", t, "calib", "obvious", plan[0].published_at)
                 for t in args.secret_types]
    for tok in plan:
        store.register(tok)
        print(f"{tok.token_id}\t-> канал {tok.channel}, тип {tok.secret_type}, "
              f"помітність {tok.visibility}")
    print(f"\nЗареєстровано {len(plan)} honeytokens. Опублікувати кожен у відповідний канал.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
