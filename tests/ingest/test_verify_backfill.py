from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from ingest_helpers import FakeDownloader, fixture_for

from breakout.config import Config
from breakout.ingest.backfill import last_complete_day, plan_days, run_hourly_backfill
from breakout.ingest.day import ingest_day
from breakout.lake import layout
from breakout.lake.verify import verify_lake
from breakout.schema import EVENTS_SCHEMA


def _rows(day: date, source: str, level: int, ids: range) -> pa.Table:
    t0 = datetime(day.year, day.month, day.day, 1)
    n = len(ids)
    cols: dict[str, list] = {f.name: [None] * n for f in EVENTS_SCHEMA}
    cols.update(
        event_id=list(ids),
        event_type=["WatchEvent"] * n,
        created_at=[t0 + timedelta(minutes=i) for i in range(n)],
        repo_id=[1] * n,
        actor_id=[2] * n,
        detail_level=[level] * n,
        source=[source] * n,
        ingested_at=[t0] * n,
    )
    return pa.table(cols, schema=EVENTS_SCHEMA)


def _write(path: Path, table: pa.Table) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path)


def test_verify_clean_lake(cfg: Config) -> None:
    _write(layout.bq_file("WatchEvent", 2023, 5, cfg), _rows(date(2023, 5, 10), "bq", 0, range(5)))
    _write(
        layout.day_file("WatchEvent", date(2023, 6, 2), cfg),
        _rows(date(2023, 6, 2), "hourly", 1, range(100, 105)),
    )
    _write(
        layout.day_file("WatchEvent", date(2015, 12, 31), cfg),  # hourly_gap_days exception
        _rows(date(2015, 12, 31), "hourly", 1, range(200, 203)),
    )
    rep = verify_lake(cfg)
    assert rep.ok, rep.violations
    assert rep.files_checked == 3
    assert rep.rows_by_era["trusted"] == 13


def test_verify_flags_each_invariant(cfg: Config) -> None:
    # bq file for the cutover month (overlaps hourly territory)
    _write(layout.bq_file("WatchEvent", 2023, 6, cfg), _rows(date(2023, 6, 5), "bq", 0, range(5)))
    # hourly day file before cutover that is not a gap day
    _write(
        layout.day_file("WatchEvent", date(2022, 1, 3), cfg),
        _rows(date(2022, 1, 3), "hourly", 1, range(10, 12)),
    )
    # bq file with detail_level 1 in the spine era
    _write(
        layout.bq_file("WatchEvent", 2022, 2, cfg), _rows(date(2022, 2, 3), "bq", 1, range(20, 22))
    )
    # duplicate event ids across files of one month
    _write(
        layout.day_file("WatchEvent", date(2024, 1, 1), cfg),
        _rows(date(2024, 1, 1), "hourly", 1, range(50, 53)),
    )
    _write(
        layout.day_file("WatchEvent", date(2024, 1, 2), cfg),
        _rows(date(2024, 1, 2), "hourly", 1, range(52, 55)),
    )
    # rows outside the file's day
    _write(
        layout.day_file("WatchEvent", date(2024, 1, 5), cfg),
        _rows(date(2024, 1, 6), "hourly", 1, range(70, 72)),
    )
    msg = "\n".join(verify_lake(cfg).violations)
    assert "not entirely before cutover" in msg
    assert "hourly day file before cutover" in msg
    assert "spine-era bq file with detail_level" in msg
    assert "duplicate event_ids across 3 file(s)" in msg
    assert "expected only 2024-01-05" in msg


def test_verify_lists_opendigger_files(cfg: Config) -> None:
    f = layout.day_file("WatchEvent", date(2024, 1, 1), cfg)
    _write(f, _rows(date(2024, 1, 1), "opendigger", 1, range(3)))
    rep = verify_lake(cfg)
    assert rep.ok and rep.opendigger_files == [f]


def test_plan_days_orders_trusted_then_degraded(cfg: Config) -> None:
    days = plan_days(cfg, start=date(2025, 5, 20), end=date(2025, 5, 27))
    assert [d.era for d in days] == ["trusted"] * 4 + ["degraded"] * 4
    assert days[3].day == date(2025, 5, 23) and days[4].day == date(2025, 5, 24)
    full = plan_days(cfg, now=datetime(2026, 10, 12, 8, tzinfo=UTC))
    assert [d.era for d in full[:4]] == ["gap"] * 4  # hourly_gap_days first
    assert full[4].day == date(2023, 6, 1) and full[-1].day == date(2026, 10, 11)
    eras = [d.era for d in full]
    assert eras.index("degraded") > max(i for i, e in enumerate(eras) if e == "trusted")


def test_last_complete_day_respects_lag(cfg: Config) -> None:
    assert last_complete_day(cfg, datetime(2026, 10, 12, 1)) == date(2026, 10, 10)
    assert last_complete_day(cfg, datetime(2026, 10, 12, 3)) == date(2026, 10, 11)


def test_backfill_workers_capped_and_resumable(cfg: Config) -> None:
    dl = FakeDownloader(fixture_for("2024-06-03"))
    days = plan_days(cfg, start=date(2024, 6, 3), end=date(2024, 6, 4))
    with pytest.raises(ValueError):
        run_hourly_backfill(cfg, days, workers=5)
    now = datetime(2030, 1, 1)
    s1 = ingest_day(date(2024, 6, 3), cfg=cfg, now=now, downloader=dl)
    assert s1.hours_ok == 24
    calls = len(dl.calls)
    # a second pass over a day already ok does no downloads
    s2 = ingest_day(date(2024, 6, 3), cfg=cfg, now=now, downloader=dl)
    assert s2.hours_processed == 0 and len(dl.calls) == calls
