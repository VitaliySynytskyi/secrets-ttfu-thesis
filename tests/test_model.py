# diploma/experiment/tests/test_model.py
import pytest
from datetime import datetime, timezone
from collector.model import Honeytoken, Hit, compute_ttc_seconds


def test_compute_ttc_seconds_basic():
    published = datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)
    first_use = datetime(2026, 7, 1, 12, 3, 30, tzinfo=timezone.utc)
    assert compute_ttc_seconds(published, first_use) == 210.0


def test_compute_ttc_seconds_rejects_negative_delta():
    published = datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)
    earlier  = datetime(2026, 7, 1, 11, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        compute_ttc_seconds(published, earlier)
