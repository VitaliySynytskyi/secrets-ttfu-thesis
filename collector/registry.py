# diploma/experiment/collector/registry.py
from __future__ import annotations
from datetime import datetime, timezone
from .model import Honeytoken

CHANNELS = ("github", "ci-log", "paste", "dotenv")
SECRET_TYPES = ("aws", "gcp", "db", "api")
# obvious: явний патерн/маркер (напр. рядок у .env з коментарем "AWS key");
# buried: те саме значення секрету, вписане непомітно (без маркера, серед звичайного коду).
VISIBILITIES = ("obvious", "buried")


def build_plan(replicas: int = 3, published_at: datetime | None = None,
               channels=CHANNELS, secret_types=SECRET_TYPES,
               visibilities=VISIBILITIES, replica_start: int = 0) -> list[Honeytoken]:
    """Згенерувати план розгортання: по `replicas` токенів на кожну комбінацію
    (канал, тип секрету, помітність). Передай вужчі `channels`/`secret_types`/
    `visibilities`, щоб згенерувати менший пілотний зріз замість повної сітки.
    `replica_start` зсуває нумерацію реплік (основна кампанія: 1..3, бо 0 — пілот)."""
    if replicas < 1:
        raise ValueError(f"replicas must be >= 1, got {replicas}")
    published_at = published_at or datetime.now(timezone.utc)
    plan: list[Honeytoken] = []
    for channel in channels:
        for secret_type in secret_types:
            for visibility in visibilities:
                for i in range(replica_start, replica_start + replicas):
                    token_id = f"{channel}-{secret_type}-{visibility}-{i}"
                    plan.append(Honeytoken(token_id, secret_type, channel, visibility, published_at))
    return plan
