"""Експорт TTFU з бази колектора в CSV для аналізу.

    .venv/Scripts/python.exe deploy/export.py --db data/ttc.db --out data/ttc.csv [--now 2026-10-31T12:00:00+00:00]
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from collector.store import TtcStore  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/ttc.db")
    ap.add_argument("--out", default="data/ttc.csv")
    ap.add_argument("--now", help="кінець вікна спостереження (ISO 8601 з часовою зоною); за замовчуванням зараз")
    ap.add_argument("--include-calib", action="store_true",
                    help="не відкидати калібрувальні токени (канал calib) — лише для перевірок")
    a = ap.parse_args(argv)
    excl = () if a.include_calib else ("calib",)
    now = datetime.fromisoformat(a.now) if a.now else datetime.now(timezone.utc)
    store = TtcStore(a.db)
    store.export_csv(a.out, now=now, exclude_channels=excl)
    rows = store.export_rows(now=now, exclude_channels=excl)
    print(f"exported {len(rows)} tokens ({sum(1 - r['censored'] for r in rows)} used) -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
