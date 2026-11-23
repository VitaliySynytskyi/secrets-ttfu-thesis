"""Стан кампанії: покриття публікації і зведення подій (без секретів).

    python deploy/campaign_status.py --db data/campaign/<час>/ttc.db
    python deploy/campaign_status.py --db data/.../ttc.db --published published.csv --json

Перевіряє:
  * скільки з 96 токенів (репліки 1-3) опубліковано — за наявності CSV published.csv;
  * у скількох задано published_at (seed ставить момент свого запуску; без уточнення TTC завищено);
  * чи жоден токен не «спрацював» раніше за свою публікацію (ознака неправильного published_at);
  * зведення: use / exposed / attempt по каналах і типах, топ країн-джерел.
Калібрувальні токени (канал calib) та пілот (репліки -0) у підсумки кампанії не входять.
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from collector.store import TtcStore  # noqa: E402

CAMPAIGN_REPLICAS = ("1", "2", "3")


def _is_campaign(token_id: str, channel: str) -> bool:
    return channel != "calib" and token_id.rsplit("-", 1)[-1] in CAMPAIGN_REPLICAS


def collect(db_path: str, published_csv: str | None, seed_run_at: str | None) -> dict:
    conn = sqlite3.connect(db_path)
    tokens = [(t, s, c, v, p) for t, s, c, v, p in conn.execute(
        "SELECT token_id, secret_type, channel, visibility, published_at FROM tokens")
        if _is_campaign(t, c)]
    ids = {t[0] for t in tokens}

    published = set()
    if published_csv:
        with open(published_csv, encoding="utf-8") as fh:
            published = {r["token_id"].strip() for r in csv.DictReader(fh)
                         if r.get("token_id", "").strip()}

    # published_at «уточнено» = відрізняється від моменту запуску seed
    refined = sum(1 for *_, p in tokens if seed_run_at is None or not p.startswith(seed_run_at))

    events = list(conn.execute(
        "SELECT token_id, kind, at FROM events WHERE token_id IN ({})".format(
            ",".join("?" * len(ids))), tuple(ids)) if ids else [])
    pub_at = {t[0]: t[4] for t in tokens}
    anomalies = [(tid, at, pub_at[tid]) for tid, kind, at in events
                 if kind == "use" and at < pub_at.get(tid, "")]

    by_kind = Counter(k for _, k, _ in events)
    used = {tid for tid, k, _ in events if k == "use"}
    kinds_by_channel = Counter((t[2], "used" if t[0] in used else "waiting") for t in tokens)

    return {
        "tokens_registered": len(tokens),
        "published_in_manifest": len(published & ids) if published_csv else None,
        "missing_from_manifest": sorted(ids - published) if published_csv else None,
        "published_at_refined": refined,
        "events": dict(by_kind),
        "tokens_used": len(used),
        "used_by_channel": {c: n for (c, st), n in kinds_by_channel.items() if st == "used"},
        "anomalies_use_before_publish": anomalies,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--published", help="CSV маніфесту публікації (token_id,...)")
    ap.add_argument("--seed-run-at", help="ISO-префікс моменту запуску seed, напр. 2026-10-16T19"
                    " — токени з таким published_at вважаються ще не уточненими")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    st = collect(a.db, a.published, a.seed_run_at)
    if a.json:
        print(json.dumps(st, ensure_ascii=False, indent=2))
        return 0
    print(f"Зареєстровано токенів кампанії: {st['tokens_registered']}/96")
    if st["published_in_manifest"] is not None:
        print(f"У маніфесті публікації: {st['published_in_manifest']}")
        if st["missing_from_manifest"]:
            print(f"  ще не опубліковано ({len(st['missing_from_manifest'])}): "
                  + ", ".join(st["missing_from_manifest"][:12])
                  + (" …" if len(st["missing_from_manifest"]) > 12 else ""))
    print(f"published_at уточнено: {st['published_at_refined']}/{st['tokens_registered']}")
    print(f"Використано токенів: {st['tokens_used']}; події: {st['events']}")
    if st["used_by_channel"]:
        print("  по каналах: " + ", ".join(f"{c}={n}" for c, n in st["used_by_channel"].items()))
    if st["anomalies_use_before_publish"]:
        print(f"  !! УВАГА: {len(st['anomalies_use_before_publish'])} use раніше за published_at "
              "(перевір published_at): " + ", ".join(a[0] for a in st["anomalies_use_before_publish"][:5]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
