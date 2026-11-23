import numpy as np
from modeling.loader import load_ttc


def test_load_ttc_splits_durations_and_events(tmp_path):
    csv = tmp_path / "ttc.csv"
    csv.write_text(
        "token_id,secret_type,channel,ttc_seconds,censored\n"
        "a,aws,github,120.0,0\n"
        "b,aws,github,86400.0,1\n",
        encoding="utf-8",
    )
    durations, events = load_ttc(csv)
    assert np.allclose(durations, [120.0, 86400.0])
    assert list(events) == [1, 0]  # censored=1 -> event=0


def test_load_ttc_filter_channel(tmp_path):
    csv = tmp_path / "ttc.csv"
    csv.write_text(
        "token_id,secret_type,channel,ttc_seconds,censored\n"
        "a,aws,github,120.0,0\n"
        "b,db,paste,300.0,0\n",
        encoding="utf-8",
    )
    durations, events = load_ttc(csv, channel="paste")
    assert np.allclose(durations, [300.0])


def test_load_ttc_filter_secret_type(tmp_path):
    csv = tmp_path / "ttc.csv"
    csv.write_text(
        "token_id,secret_type,channel,ttc_seconds,censored\n"
        "a,aws,github,120.0,0\n"
        "b,db,paste,300.0,0\n",
        encoding="utf-8",
    )
    durations, events = load_ttc(csv, secret_type="db")
    assert np.allclose(durations, [300.0])
