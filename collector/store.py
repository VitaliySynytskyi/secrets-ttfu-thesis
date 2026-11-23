# diploma/experiment/collector/store.py
from __future__ import annotations
import csv
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .model import Honeytoken, Hit, compute_ttc_seconds


class TtcStore:
    def __init__(self, db_path: Path | str):
        self.db_path = str(db_path)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS tokens ("
            "token_id TEXT PRIMARY KEY, secret_type TEXT, channel TEXT, "
            "visibility TEXT, published_at TEXT)"
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS hits ("
            "token_id TEXT, used_at TEXT, source_ip TEXT)"
        )
        # Усі події Canarytokens: use | safety_net | exposed (див. collector/canarytokens.py).
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS events ("
            "token_id TEXT, kind TEXT, at TEXT, source_ip TEXT, public_location TEXT)"
        )
        self._conn.commit()

    def register(self, tok: Honeytoken) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO tokens VALUES (?,?,?,?,?)",
            (tok.token_id, tok.secret_type, tok.channel, tok.visibility,
             tok.published_at.isoformat()),
        )
        self._conn.commit()

    def known_token(self, token_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM tokens WHERE token_id = ?", (token_id,)
        ).fetchone()
        return row is not None

    def set_published_at(self, token_id: str, published_at: datetime) -> None:
        self._conn.execute("UPDATE tokens SET published_at = ? WHERE token_id = ?",
                           (published_at.isoformat(), token_id))
        self._conn.commit()

    def clear_events(self) -> None:
        """Очистити похідні таблиці (hits, events) перед перебудовою з сирого журналу."""
        self._conn.execute("DELETE FROM hits")
        self._conn.execute("DELETE FROM events")
        self._conn.commit()

    def token_count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM tokens").fetchone()[0]

    def record_hit(self, hit: Hit) -> None:
        self._conn.execute(
            "INSERT INTO hits VALUES (?,?,?)",
            (hit.token_id, hit.used_at.isoformat(), hit.source_ip),
        )
        self._conn.commit()

    def record_event(self, ev) -> None:
        """Зберегти подію Canarytokens. Лише `use` є точним моментом першого використання
        і потрапляє в hits; safety_net і exposed аналізуються окремо."""
        self._conn.execute(
            "INSERT INTO events VALUES (?,?,?,?,?)",
            (ev.token_id, ev.kind, ev.at.isoformat(), ev.source_ip, ev.public_location),
        )
        if ev.kind == "use":
            self._conn.execute("INSERT INTO hits VALUES (?,?,?)",
                               (ev.token_id, ev.at.isoformat(), ev.source_ip))
        self._conn.commit()

    def _first_event(self, token_id: str, kind: str):
        v = self._conn.execute(
            "SELECT MIN(at) FROM events WHERE token_id = ? AND kind = ?", (token_id, kind)
        ).fetchone()[0]
        return datetime.fromisoformat(v) if v else None

    def export_rows(self, now: datetime | None = None,
                    exclude_channels: tuple[str, ...] = ()) -> list[dict]:
        now = now or datetime.now(timezone.utc)
        rows: list[dict] = []
        for token_id, secret_type, channel, visibility, published_iso in self._conn.execute(
            "SELECT token_id, secret_type, channel, visibility, published_at FROM tokens"
        ).fetchall():
            if channel in exclude_channels:
                continue
            published = datetime.fromisoformat(published_iso)
            first = self._conn.execute(
                "SELECT MIN(used_at) FROM hits WHERE token_id = ?", (token_id,)
            ).fetchone()[0]
            safety = self._first_event(token_id, "safety_net")
            exposed = self._first_event(token_id, "exposed")
            time_precise = 1
            if first is not None:
                ttc = compute_ttc_seconds(published, datetime.fromisoformat(first))
                censored = 0
            elif safety is not None:
                # використання підтверджене звітом IAM, але момент відомий лише як верхня межа
                ttc = compute_ttc_seconds(published, safety)
                censored, time_precise = 0, 0
            else:
                ttc = max(0.0, (now - published).total_seconds())
                censored = 1
            rows.append({
                "token_id": token_id, "secret_type": secret_type, "channel": channel,
                "visibility": visibility, "ttc_seconds": ttc, "censored": censored,
                "time_precise": time_precise,
                "exposed_seconds": compute_ttc_seconds(published, exposed) if exposed else "",
            })
        return rows

    def export_csv(self, out_path: Path | str, now: datetime | None = None,
                   exclude_channels: tuple[str, ...] = ()) -> None:
        rows = self.export_rows(now=now, exclude_channels=exclude_channels)
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(
                fh, fieldnames=["token_id", "secret_type", "channel", "visibility",
                                "ttc_seconds", "censored", "time_precise", "exposed_seconds"]
            )
            writer.writeheader()
            writer.writerows(rows)
