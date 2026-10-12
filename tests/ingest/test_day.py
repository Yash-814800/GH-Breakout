from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb
import pyarrow.parquet as pq
from ingest_helpers import RAW_TYPES, FakeDownloader, fixture_for

from breakout.config import Config
from breakout.ingest import manifest as mf
from breakout.ingest.day import ingest_day
from breakout.ingest.parse import parse_hour_file
from breakout.lake import layout
from breakout.schema import EVENTS_SCHEMA, PARSER_VERSION, PUSH_DAILY_SCHEMA

NOW = datetime(2030, 1, 1)
DAY = date(2024, 6, 3)


def _expected(fixture: Path, day: date):
    r = parse_hour_file(fixture, datetime(day.year, day.month, day.day, 12), raw_types=RAW_TYPES)
    return r


def _checksum(files: list[Path]) -> str:
    """Hash of the sorted content keys: event ids for events, (repo, actor, n) for push."""
    keys: list[str] = []
    for f in files:
        t = pq.read_table(f)
        if "event_id" in t.column_names:
            keys.extend(str(i) for i in t.column("event_id").to_pylist())
        else:
            cols = [t.column(c).to_pylist() for c in ("repo_id", "actor_id", "n_pushes")]
            keys.extend("/".join(map(str, row)) for row in zip(*cols, strict=True))
    return hashlib.sha256(",".join(sorted(keys)).encode()).hexdigest()


def _all_files(cfg: Config) -> list[Path]:
    return sorted(layout.lake_root(cfg).rglob("day-*.parquet"))


def test_ingest_day_builds_files_and_manifest(cfg: Config) -> None:
    fx = fixture_for("2024-06-03")
    dl = FakeDownloader(fx)
    s = ingest_day(DAY, cfg=cfg, now=NOW, downloader=dl)
    assert s.hours_ok == 24 and s.hours_processed == 24 and not s.missing_hours
    expected = _expected(fx, DAY)
    # every hour served the same file; dedupe must collapse them to one copy
    for etype in cfg.events.raw_types:
        f = layout.day_file(etype, DAY, cfg)
        assert f.exists(), etype
        t = pq.read_table(f)
        assert t.num_rows == s.rows_per_type[etype]
        want = sum(1 for e in expected.events.to_pylist() if e["event_type"] == etype)
        assert t.num_rows == want
        ids = t.column("event_id").to_pylist()
        assert len(ids) == len(set(ids))
        assert set(t.column("event_type").to_pylist()) == {etype}
    push = pq.read_table(layout.day_file("PushEvent", DAY, cfg))
    assert push.schema.names == PUSH_DAILY_SCHEMA.names
    assert sum(push.column("n_pushes").to_pylist()) == expected.push_rows.num_rows
    assert set(push.column("day").to_pylist()) == {DAY}
    ev = pq.read_table(layout.day_file("WatchEvent", DAY, cfg))
    assert ev.schema.names == EVENTS_SCHEMA.names
    rows = mf.HourlyManifest(layout.hourly_manifest_path(cfg)).load()
    assert len(rows) == 24
    assert {r.status for r in rows.values()} == {mf.OK}
    assert {r.parser_version for r in rows.values()} == {PARSER_VERSION}
    assert not list((layout.raw_dir(cfg) / DAY.isoformat()).glob("*.json.gz"))


def test_ingest_day_is_idempotent(cfg: Config) -> None:
    dl = FakeDownloader(fixture_for("2024-06-03"))
    ingest_day(DAY, cfg=cfg, now=NOW, downloader=dl)
    files = _all_files(cfg)
    assert len(files) == 10  # 9 event types + push_daily
    before = {f: f.read_bytes() for f in files}
    manifest_before = layout.hourly_manifest_path(cfg).read_bytes()
    checksum = _checksum(files)
    calls = len(dl.calls)

    s2 = ingest_day(DAY, cfg=cfg, now=NOW + timedelta(hours=5), downloader=dl)
    assert len(dl.calls) == calls  # no downloads
    assert s2.hours_processed == 0 and s2.hours_skipped == 24
    assert {f: f.read_bytes() for f in _all_files(cfg)} == before
    assert layout.hourly_manifest_path(cfg).read_bytes() == manifest_before
    assert _checksum(_all_files(cfg)) == checksum


def test_force_reingests_with_same_content(cfg: Config) -> None:
    dl = FakeDownloader(fixture_for("2024-06-03"))
    ingest_day(DAY, cfg=cfg, now=NOW, downloader=dl)
    checksum = _checksum(_all_files(cfg))
    s = ingest_day(DAY, cfg=cfg, now=NOW, downloader=dl, force=True)
    assert s.hours_processed == 24
    assert _checksum(_all_files(cfg)) == checksum


def test_missing_hours_pending_then_missing_and_retry(cfg: Config) -> None:
    fx = fixture_for("2024-06-03")
    dl = FakeDownloader(fx, missing={3, 4})
    now = datetime(2024, 6, 4, 6)  # one day after the data day -> inside the 3-day window
    s = ingest_day(DAY, cfg=cfg, now=now, downloader=dl)
    assert s.pending_hours == [3, 4] and s.hours_ok == 22
    # the hours arrive late
    dl2 = FakeDownloader(fx)
    s2 = ingest_day(DAY, cfg=cfg, now=now + timedelta(hours=1), downloader=dl2)
    assert sorted(c.hour for c in dl2.calls) == [3, 4]
    assert s2.hours_ok == 24
    # hours that never show up become 'missing' after the window and are not retried
    cfg_day = date(2024, 6, 10)
    dl3 = FakeDownloader(fixture_for("2024-06-03"), missing={0})
    late = datetime(2024, 6, 20)
    s3 = ingest_day(cfg_day, cfg=cfg, now=late, downloader=dl3)
    assert s3.missing_hours == [0]
    dl4 = FakeDownloader(fixture_for("2024-06-03"))
    ingest_day(cfg_day, cfg=cfg, now=late, downloader=dl4)
    assert dl4.calls == []


def test_error_hours_are_retried(cfg: Config) -> None:
    from breakout.ingest.gharchive import DownloadResult

    fx = fixture_for("2024-06-03")
    good = FakeDownloader(fx)

    def flaky(ts, dest):
        if ts.hour == 7:
            return DownloadResult("error", error="boom", attempts=5)
        return good(ts, dest)

    s = ingest_day(DAY, cfg=cfg, now=NOW, downloader=flaky)
    assert s.error_hours == [7] and s.hours_ok == 23
    s2 = ingest_day(DAY, cfg=cfg, now=NOW, downloader=FakeDownloader(fx))
    assert s2.hours_ok == 24 and s2.hours_processed == 1


def test_boundary_events_spill_into_their_own_day(cfg: Config) -> None:
    fx = fixture_for("2024-06-03")  # contains events dated 2024-06-03 only
    expected = _expected(fx, DAY)
    # Serve a 2024-06-03 file as hour 0 of 2024-06-04: all its events are spillover.
    dl = FakeDownloader(fx)
    s = ingest_day(date(2024, 6, 4), cfg=cfg, now=NOW, downloader=dl, only_hours={0})
    assert s.hours_ok == 1
    spill = layout.staging_dir(cfg) / "2024-06-03" / "spill-from-2024-06-04.events.parquet"
    assert spill.exists()
    n_in_spill = pq.read_table(spill).num_rows
    assert n_in_spill == expected.events.num_rows
    # the spilled day is not fully staged, so its file is built when that day is ingested
    assert not layout.day_file("WatchEvent", DAY, cfg).exists()
    # day 2024-06-04 itself has no rows for those events
    assert pq.read_table(layout.day_file("WatchEvent", date(2024, 6, 4), cfg)).num_rows == 0
    ingest_day(DAY, cfg=cfg, now=NOW, downloader=FakeDownloader(fx))
    t = pq.read_table(layout.day_file("WatchEvent", DAY, cfg))
    want = sum(1 for e in expected.events.to_pylist() if e["event_type"] == "WatchEvent")
    assert t.num_rows == want


def test_day_file_sorted_and_zstd(cfg: Config) -> None:
    ingest_day(DAY, cfg=cfg, now=NOW, downloader=FakeDownloader(fixture_for("2024-06-03")))
    f = layout.day_file("IssueCommentEvent", DAY, cfg)
    md = pq.ParquetFile(f).metadata
    assert md.row_group(0).column(0).compression == "ZSTD"
    rows = duckdb.sql(f"select repo_id, created_at, event_id from '{f}'").fetchall()
    assert rows == sorted(rows)
