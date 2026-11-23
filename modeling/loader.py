from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd


def load_ttc(csv_path: Path | str, channel: str | None = None,
             secret_type: str | None = None, visibility: str | None = None):
    """Прочитати ttc.csv -> (durations, events). event=1 спостережено, 0 цензуровано."""
    df = pd.read_csv(csv_path)
    if channel is not None:
        df = df[df["channel"] == channel]
    if secret_type is not None:
        df = df[df["secret_type"] == secret_type]
    if visibility is not None:
        df = df[df["visibility"] == visibility]
    durations = df["ttc_seconds"].to_numpy(dtype=float)
    events = (1 - df["censored"].to_numpy(dtype=int))
    return durations, events


def distinct_strata(csv_path):
    """Return {"channels":[...], "secret_types":[...], "visibilities":[...]} present in the CSV.
    Старі датасети без колонки visibility дають порожній список."""
    df = pd.read_csv(csv_path)
    vis = sorted(df["visibility"].unique().tolist()) if "visibility" in df else []
    return {"channels": sorted(df["channel"].unique().tolist()),
            "secret_types": sorted(df["secret_type"].unique().tolist()),
            "visibilities": vis}
