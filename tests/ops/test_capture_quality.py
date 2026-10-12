from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from breakout.ops import capture_quality as cq


def _write(tmp_path: Path) -> Path:
    days, rows = date(2024, 1, 1), []
    d = days
    while d <= date(2025, 3, 31):
        factor = 1.0 if d < date(2025, 2, 1) else 0.4
        rows.append(
            {
                "day": d,
                "total": 1000,
                "watch": int(100 * factor),
                "fork": 10,
                "issues": 50,
                "pr": 70,
            }
        )
        d += timedelta(days=1)
    p = tmp_path / "daily.parquet"
    pq.write_table(pa.Table.from_pylist(rows), p)
    return p


def test_ratio_is_vs_same_weekday_median_of_baseline_year(tmp_path: Path) -> None:
    rows = cq.build_table(_write(tmp_path))
    jan = next(r for r in rows if r["day"] == date(2025, 1, 15))
    mar = next(r for r in rows if r["day"] == date(2025, 3, 15))
    assert jan["ratio_watch"] == 1.0
    assert abs(mar["ratio_watch"] - 0.4) < 1e-9
    assert abs(mar["ratio_watch_per_issue"] - 0.4) < 1e-9
    assert mar["ratio_total"] == 1.0


def test_first_sustained_drop_and_monthly(tmp_path: Path) -> None:
    rows = cq.build_table(_write(tmp_path))
    assert cq.first_sustained_drop(rows, "ratio_watch", 0.8) == date(2025, 2, 1)
    assert cq.first_sustained_drop(rows, "ratio_watch", 0.2) is None
    months = {m["month"]: m for m in cq.monthly(rows)}
    assert months["2025-03"]["ratio_watch"] < 0.5 <= months["2025-01"]["ratio_watch"]
