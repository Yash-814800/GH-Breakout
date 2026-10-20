"""A deleted manifest hour is planned again; once re-ingested the plan is empty (idempotent)."""

from datetime import datetime

from breakout.ingest.manifest import OK, HourlyManifest, ManifestRow, iter_hours
from breakout.schema import PARSER_VERSION

START, END = datetime(2026, 10, 1), datetime(2026, 10, 2)
NOW = datetime(2026, 10, 5)


def _row(h: datetime) -> ManifestRow:
    return ManifestRow(hour_ts=h, status=OK, parser_version=PARSER_VERSION)


def _plan(m: HourlyManifest) -> list[datetime]:
    return m.hours_needing_work(START, END, NOW, parser_version=PARSER_VERSION, min_hour_lag=2)


def test_gap_hour_is_reingested_then_plan_is_empty(tmp_path):
    m = HourlyManifest(tmp_path / "hourly_manifest.parquet")
    hours = list(iter_hours(START, END))
    m.upsert([_row(h) for h in hours])
    assert _plan(m) == []

    gap = hours[7]
    kept = {h: r for h, r in m.load().items() if h != gap}
    (tmp_path / "hourly_manifest.parquet").unlink()
    m.upsert(list(kept.values()))
    assert _plan(m) == [gap]

    m.upsert([_row(gap)])
    assert _plan(m) == []
