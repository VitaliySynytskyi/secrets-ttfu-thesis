"""Перебудувати таблиці hits/events з сирого журналу webhook-ів (raw-events.jsonl).

Сирий журнал — первинне джерело; база — похідна. Після зміни правил класифікації в
collector/canarytokens.py цей скрипт перераховує події, не чіпаючи таблицю tokens:

    python deploy/rebuild_from_raw.py --db data/ttc.db --raw data/raw-events.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from collector.app import CANARYTOKENS_TEST_TOKEN  # noqa: E402
from collector.canarytokens import parse_canarytokens_payload  # noqa: E402
from collector.store import TtcStore  # noqa: E402


def rebuild(store: TtcStore, raw_path: Path) -> Counter:
    stats: Counter = Counter()
    store.clear_events()
    for line in raw_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)["payload"]
        if payload.get("token") == CANARYTOKENS_TEST_TOKEN:
            stats["webhook-test"] += 1
            continue
        try:
            ev = parse_canarytokens_payload(payload)
        except (ValueError, TypeError):
            stats["unparseable"] += 1
            continue
        if not store.known_token(ev.token_id):
            stats["unknown-token"] += 1
            continue
        store.record_event(ev)
        stats[ev.kind] += 1
    return stats


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/ttc.db")
    ap.add_argument("--raw", default="data/raw-events.jsonl")
    a = ap.parse_args(argv)
    stats = rebuild(TtcStore(a.db), Path(a.raw))
    print(", ".join(f"{k}={v}" for k, v in sorted(stats.items())) or "журнал порожній")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
