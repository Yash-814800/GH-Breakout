from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

from breakout.config import get_config
from breakout.ml import append_live


def test_find_matured_live_mondays(tmp_path: Path, monkeypatch) -> None:
    live_feat_dir = tmp_path / "live" / "features"
    live_feat_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(append_live, "LIVE_FEATURES_DIR", live_feat_dir)

    # Create dummy live feature files for Mondays and non-Mondays
    # 2024-06-03 was a Monday. 30 days horizon -> matured by 2024-07-04.
    (live_feat_dir / "date=2024-06-03.parquet").touch()
    # 2024-06-04 was a Tuesday (should be ignored by Monday append)
    (live_feat_dir / "date=2024-06-04.parquet").touch()
    # 2024-07-01 was a Monday. Horizon 30d -> matured by 2024-08-01 (not yet matured on 2024-07-15)
    (live_feat_dir / "date=2024-07-01.parquet").touch()

    cfg = get_config(None)
    # Latest ingested date: 2024-07-15
    matured = append_live.find_matured_live_mondays(cfg, latest_ingested=date(2024, 7, 15))
    assert len(matured) == 1
    assert matured[0][0] == date(2024, 6, 3)


def test_compute_live_labels_synthetic(tmp_path: Path) -> None:
    # Test compute_live_labels logic with DuckDB
    con = duckdb.connect()
    con.execute(
        """
        create table int_repo_star_daily as
        select 101 as repo_id, date '2024-06-05' as day, 2 as n_stars
        union all
        select 102 as repo_id, date '2024-06-06' as day, 1 as n_stars;

        create table stg_trending as
        select 101 as repo_id, date '2024-06-15' as trending_date,
               cast(null as varchar) as language_filter;
        """
    )

    cfg = get_config(None)
    snap_d = date(2024, 6, 3)
    cand_ids = [101, 102]

    df = append_live.compute_live_labels(cfg, snap_d, cand_ids, con=con)
    assert len(df) == 2
    row_101 = df[df["repo_id"] == 101].iloc[0]
    row_102 = df[df["repo_id"] == 102].iloc[0]

    assert row_101["gain_30d"] == 2
    assert row_102["gain_30d"] == 1
    assert pd.to_datetime(row_101["first_trending_date"]).date() == date(2024, 6, 15)
    assert pd.isna(row_102["first_trending_date"])
