from __future__ import annotations

from datetime import date, datetime

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from breakout.lake import catalog as cat
from breakout.lake import hf


def test_build_catalog_reads_footers(lake):
    lake.day(date(2024, 6, 3), n=5)
    lake.bq("WatchEvent", 2022, 1, n=3)
    junk = lake.root / "events/event_type=WatchEvent/year=2024/month=06/day-2024-06-04.parquet.tmp"
    junk.write_bytes(b"x")
    (
        lake.root / "events/event_type=WatchEvent/year=2024/month=06/spill-from-x.parquet"
    ).write_bytes(b"x")
    table = cat.build_catalog(lake.root)
    rows = {r["path"]: r for r in table.to_pylist()}
    assert len(rows) == 4  # 2 types + push_daily day files + one bq file; junk excluded
    w = rows["events/event_type=WatchEvent/year=2024/month=06/day-2024-06-03.parquet"]
    assert (w["table"], w["event_type"], w["kind"], w["day"]) == (
        "events",
        "WatchEvent",
        "day",
        date(2024, 6, 3),
    )
    assert w["rows"] == 5 and w["detail_level_min"] == w["detail_level_max"] == 1
    assert w["source_min"] == w["source_max"] == "hourly"
    assert w["min_created_at"].date() == w["max_created_at"].date() == date(2024, 6, 3)
    assert w["schema_version"] == 1 and len(w["sha256"]) == 64
    b = rows["events/event_type=WatchEvent/year=2022/month=01/bq-202201.parquet"]
    assert b["kind"] == "bq" and b["detail_level_max"] == 0 and b["source_max"] == "bq"
    p = rows["push_daily/year=2024/month=06/day-2024-06-03.parquet"]
    assert p["table"] == "push_daily" and p["event_type"] is None
    assert p["min_created_at"] == datetime(2024, 6, 3)
    assert p["rows"] == 5


def test_schema_version_zero_on_drift(lake, cfg):
    f = lake.day(date(2024, 6, 3))[0]
    t = pq.read_table(f).drop_columns(["org_id"])
    pq.write_table(t, f)
    row = cat.build_catalog(lake.root, files=[f]).to_pylist()[0]
    assert row["schema_version"] == 0


def test_sha_cache_roundtrip(lake, tmp_path):
    f = lake.day(date(2024, 6, 3))[0]
    cache = hf.ShaCache(tmp_path / "c.json")
    a = cat.build_catalog(lake.root, files=[f], cache=cache)
    cache.save()
    again = hf.ShaCache(tmp_path / "c.json")
    assert again._data  # persisted
    b = cat.build_catalog(lake.root, files=[f], cache=again)
    assert a.to_pylist() == b.to_pylist()


def _row(table, etype, y, m, kind, day=None, path=None):
    return {
        "path": path or f"{table}/{etype}/{y}-{m}/{kind}-{day}.parquet",
        "table": table,
        "event_type": etype,
        "year": y,
        "month": m,
        "kind": kind,
        "day": day,
        "rows": 1,
        "bytes": 1,
        "sha256": "0" * 64,
        "schema_version": 1,
    }


@pytest.fixture
def catalog():
    rows = [
        _row("events", "WatchEvent", 2022, 12, "bq"),
        _row("events", "WatchEvent", 2023, 5, "bq"),
        _row("events", "WatchEvent", 2023, 6, "month"),
        _row("events", "WatchEvent", 2023, 6, "day", date(2023, 6, 3), path="stale-day"),
        _row("events", "WatchEvent", 2023, 7, "day", date(2023, 7, 1)),
        _row("events", "WatchEvent", 2023, 7, "day", date(2023, 7, 2)),
        _row("events", "WatchEvent", 2023, 7, "day", date(2023, 7, 3)),
        _row("events", "ForkEvent", 2023, 7, "day", date(2023, 7, 2)),
        _row("push_daily", None, 2023, 7, "day", date(2023, 7, 2)),
    ]
    return pa.Table.from_pylist(rows, schema=cat.CATALOG_SCHEMA)


def test_select_month_supersedes_day_and_bq(catalog):
    got = cat.select_files(catalog, "events", ["WatchEvent"], date(2023, 6, 1), date(2023, 6, 30))
    assert got == ["events/WatchEvent/2023-6/month-None.parquet"]


def test_select_days_inside_range_only(catalog):
    got = cat.select_files(catalog, "events", ["WatchEvent"], date(2023, 7, 2), date(2023, 7, 2))
    assert got == ["events/WatchEvent/2023-7/day-2023-07-02.parquet"]
    got = cat.select_files(catalog, "events", ["WatchEvent"], date(2023, 7, 2), None)
    assert [g.split("/")[-1] for g in got] == ["day-2023-07-02.parquet", "day-2023-07-03.parquet"]


def test_select_bq_months_overlapping_range_whole(catalog):
    got = cat.select_files(catalog, "events", ["WatchEvent"], date(2022, 12, 31), date(2023, 5, 2))
    assert [g.split("/")[2] for g in got] == ["2022-12", "2023-5"]


def test_select_filters_types_and_tables(catalog):
    assert len(cat.select_files(catalog, "events", None, date(2023, 7, 1), date(2023, 7, 3))) == 4
    assert cat.select_files(catalog, "events", ["ForkEvent"], date(2023, 7, 1), None)
    assert cat.select_files(catalog, "events", [], None, None) == []
    assert cat.select_files(catalog, "push_daily", None, None, None) == [
        "push_daily/None/2023-7/day-2023-07-02.parquet"
    ]


def test_merge_catalogs_replaces_and_removes(catalog):
    upd = pa.Table.from_pylist(
        [_row("events", "WatchEvent", 2023, 7, "month", path="new")], schema=cat.CATALOG_SCHEMA
    )
    out = cat.merge_catalogs(catalog, upd, removed_paths=["stale-day"])
    paths = out.column("path").to_pylist()
    assert "new" in paths and "stale-day" not in paths
    assert paths == sorted(paths)
