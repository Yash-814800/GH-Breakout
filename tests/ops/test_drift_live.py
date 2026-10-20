"""Live feature files are named ``date=YYYY-MM-DD.parquet`` and must be found by date."""

from datetime import date

import pandas as pd

from breakout import paths as P
from breakout.ops import drift


def test_find_recent_live_features_reads_date_named_files(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "DERIVED_DIR", tmp_path)
    live = tmp_path / "live" / "features"
    live.mkdir(parents=True)
    pd.DataFrame({"repo_id": [1]}).to_parquet(live / "date=2026-10-12.parquet")
    pd.DataFrame({"repo_id": [2]}).to_parquet(live / "date=2026-01-05.parquet")

    got = drift.find_recent_live_features(date(2026, 10, 19), window_days=28)

    assert got is not None and got["repo_id"].tolist() == [1]
