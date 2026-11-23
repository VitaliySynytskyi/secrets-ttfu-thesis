"""Зафіксувати точний момент публікації honeytoken (= час коміту / пасти / логу).

    python deploy/set_published.py --db data/ttc.db github-aws-obvious-0 2026-10-07T14:30:00+00:00
    python deploy/set_published.py --db data/ttc.db --from-csv published.csv   # пакетно

CSV для пакетного режиму: колонки token_id, published_at (інші колонки ігноруються).

Час обов'язково з часовою зоною; для коміту його дає `git log -1 --format=%cI`.
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from collector.store import TtcStore  # noqa: E402


def _aware(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        raise argparse.ArgumentTypeError("потрібен час із часовою зоною, напр. +00:00")
    return dt


def _batch(store: TtcStore, path: str) -> int:
    """Усі рядки перевіряються до запису: одна помилка => нічого не змінено."""
    with open(path, encoding="utf-8") as fh:
        rows = [(r["token_id"].strip(), r["published_at"].strip()) for r in csv.DictReader(fh)]
    errors, parsed = [], []
    for tid, ts in rows:
        if not store.known_token(tid):
            errors.append(f"невідомий token_id: {tid}")
            continue
        try:
            parsed.append((tid, _aware(ts)))
        except (ValueError, argparse.ArgumentTypeError) as exc:
            errors.append(f"{tid}: {exc}")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    for tid, dt in parsed:
        store.set_published_at(tid, dt)
    print(f"оновлено published_at для {len(parsed)} токенів")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/ttc.db")
    ap.add_argument("--from-csv", help="пакетно: CSV з колонками token_id, published_at")
    ap.add_argument("token_id", nargs="?")
    ap.add_argument("published_at", nargs="?", type=_aware)
    a = ap.parse_args(argv)
    store = TtcStore(a.db)
    if a.from_csv:
        return _batch(store, a.from_csv)
    if not (a.token_id and a.published_at):
        ap.error("потрібні token_id і published_at або --from-csv")
    if not store.known_token(a.token_id):
        print(f"невідомий token_id: {a.token_id}", file=sys.stderr)
        return 1
    store.set_published_at(a.token_id, a.published_at)
    print(f"{a.token_id}: published_at = {a.published_at.isoformat()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
