from __future__ import annotations

from datetime import date
from pathlib import Path

from breakout.config import Config
from breakout.lake import layout


def test_paths_use_two_digit_months(cfg: Config) -> None:
    root = layout.lake_root(cfg)
    f = layout.day_file("WatchEvent", date(2024, 6, 3), cfg)
    assert f == root / "events/event_type=WatchEvent/year=2024/month=06/day-2024-06-03.parquet"
    assert layout.bq_file("ForkEvent", 2019, 1, cfg) == (
        root / "events/event_type=ForkEvent/year=2019/month=01/bq-201901.parquet"
    )
    assert layout.month_file("PushEvent", 2024, 12, cfg) == (
        root / "push_daily/year=2024/month=12/month-202412.parquet"
    )
    assert layout.hourly_manifest_path(cfg) == root / "manifests/hourly_manifest.parquet"
    assert layout.bq_manifest_path(cfg) == root / "manifests/bq_backfill.json"


def _touch(p: Path) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")
    return p


def test_glob_for_filters_and_prefers_compacted_month(cfg: Config) -> None:
    bq = _touch(layout.bq_file("WatchEvent", 2024, 5, cfg))
    d1 = _touch(layout.day_file("WatchEvent", date(2024, 6, 1), cfg))
    d2 = _touch(layout.day_file("WatchEvent", date(2024, 6, 20), cfg))
    assert layout.glob_for("WatchEvent", cfg=cfg) == [bq, d1, d2]
    assert layout.glob_for("WatchEvent", date(2024, 6, 10), cfg=cfg) == [d2]
    assert layout.glob_for("WatchEvent", end=date(2024, 5, 31), cfg=cfg) == [bq]
    assert layout.glob_for("ForkEvent", cfg=cfg) == []
    month = _touch(layout.month_file("WatchEvent", 2024, 6, cfg))
    assert layout.glob_for("WatchEvent", cfg=cfg) == [bq, month]
