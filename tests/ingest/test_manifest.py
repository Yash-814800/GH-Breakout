from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from breakout.ingest import manifest as mf

H = datetime(2024, 6, 1, 5)


def _row(status: str, hour: datetime = H, version: int = 1) -> mf.ManifestRow:
    return mf.ManifestRow(hour, status, 10, 100, "ab", 1, hour, version)


def test_upsert_roundtrip_and_replace(tmp_path: Path) -> None:
    m = mf.HourlyManifest(tmp_path / "m.parquet")
    assert m.load() == {}
    m.upsert([_row(mf.PENDING), _row(mf.OK, H + timedelta(hours=1))])
    m.upsert([_row(mf.OK)])
    rows = m.load()
    assert set(rows) == {H, H + timedelta(hours=1)}
    assert rows[H].status == mf.OK
    assert not list(tmp_path.glob("*.tmp"))


def test_status_for_404_window() -> None:
    hour_end = H + timedelta(hours=1)
    assert mf.status_for_404(H, hour_end + timedelta(days=3), 3) == mf.PENDING
    assert mf.status_for_404(H, hour_end + timedelta(days=3, seconds=1), 3) == mf.MISSING
    assert mf.status_for_404(H, hour_end + timedelta(hours=1), 3) == mf.PENDING


def _work(m: mf.HourlyManifest, now: datetime, **kw) -> list[datetime]:
    return m.hours_needing_work(
        H, H + timedelta(hours=1), now, parser_version=kw.pop("parser_version", 1), **kw
    )


def test_pending_becomes_missing_with_frozen_clock(tmp_path: Path) -> None:
    m = mf.HourlyManifest(tmp_path / "m.parquet")
    m.upsert([_row(mf.PENDING)])
    end = H + timedelta(hours=1)
    assert _work(m, end + timedelta(days=1), late_hour_retry_days=3) == [H]
    assert _work(m, end + timedelta(days=3), late_hour_retry_days=3) == [H]
    assert _work(m, end + timedelta(days=3, hours=1), late_hour_retry_days=3) == []


def test_ok_error_missing_and_version_rules(tmp_path: Path) -> None:
    m = mf.HourlyManifest(tmp_path / "m.parquet")
    now = H + timedelta(days=1)
    assert _work(m, now) == [H]  # no row
    m.upsert([_row(mf.OK)])
    assert _work(m, now) == []
    assert _work(m, now, parser_version=2) == [H]  # parser bumped
    assert _work(m, now, force=True) == [H]
    m.upsert([_row(mf.ERROR)])
    assert _work(m, now) == [H]
    m.upsert([_row(mf.MISSING)])
    assert _work(m, now) == []
    assert _work(m, now, force=True) == [H]


def test_hours_not_yet_ready_are_skipped(tmp_path: Path) -> None:
    m = mf.HourlyManifest(tmp_path / "m.parquet")
    end = H + timedelta(hours=1)
    assert _work(m, end + timedelta(hours=1), min_hour_lag=2) == []
    assert _work(m, end + timedelta(hours=2), min_hour_lag=2) == [H]
