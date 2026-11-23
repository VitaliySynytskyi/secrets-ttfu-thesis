# diploma/experiment/collector/model.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Honeytoken:
    token_id: str
    secret_type: str   # aws | gcp | db | api
    channel: str       # github | ci-log | paste | dotenv
    visibility: str    # obvious (розпізнаваний патерн/явне розміщення) | buried (прихований у звичайному коді)
    published_at: datetime

    def __post_init__(self):
        if self.published_at.tzinfo is None:
            raise ValueError("datetime must be timezone-aware")


@dataclass(frozen=True)
class Hit:
    token_id: str
    used_at: datetime
    source_ip: str

    def __post_init__(self):
        if self.used_at.tzinfo is None:
            raise ValueError("datetime must be timezone-aware")


def compute_ttc_seconds(published_at: datetime, first_use_at: datetime) -> float:
    """Time-to-compromise у секундах між публікацією і першим використанням."""
    delta = (first_use_at - published_at).total_seconds()
    if delta < 0:
        raise ValueError("first_use_at earlier than published_at")
    return float(delta)
