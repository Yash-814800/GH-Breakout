"""Backfill runner tests: manifest state machine, finalization, quota stop. No BigQuery calls."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
import pyarrow as pa
import pytest

from breakout.config import Config, load_config
from breakout.ingest.bq import run as R
from breakout.lake import layout

UTC_TS = pa.timestamp("us", tz="UTC")
DETAIL_INT = ["number", "target_user_id", "forkee_repo_id"]
DETAIL_BOOL = ["is_pull_request", "pr_merged", "release_prerelease"]
DETAIL_STR = ["action", "review_state", "ref_type"]


def _batch(rows: list[tuple[int, str, datetime, int]]) -> pa.RecordBatch:
    """rows: (event_id, event_type, created_at, repo_id)."""
    n = len(rows)
    cols = {
        "event_id": pa.array([r[0] for r in rows], pa.int64()),
        "event_type": pa.array([r[1] for r in rows]),
        "created_at": pa.array([r[2].replace(tzinfo=UTC) for r in rows], UTC_TS),
        "repo_id": pa.array([r[3] for r in rows], pa.int64()),
        "repo_name": pa.array([f"o/r{r[3]}" for r in rows]),
        "actor_id": pa.array([7] * n, pa.int64()),
        "actor_login": pa.array(["u"] * n),
        "org_id": pa.array([None] * n, pa.int64()),
        "target_created_at": pa.array([None] * n, UTC_TS),
    }
    for c in DETAIL_INT:
        cols[c] = pa.array([None] * n, pa.int64())
    for c in DETAIL_BOOL:
        cols[c] = pa.array([None] * n, pa.bool_())
    for c in DETAIL_STR:
        cols[c] = pa.array([None] * n, pa.string())
    return pa.Table.from_pydict(cols).to_batches()[0]


class _Job:
    def __init__(self, batches, billed, dry):
        self._b, self.job_id = batches, "job-1"
        self.total_bytes_processed = billed
        self.total_bytes_billed = 0 if dry else billed

    def result(self):
        return self

    def to_arrow_iterable(self, bqstorage_client=None):
        return iter(self._b)


class FakeClient:
    def __init__(self, per_unit_bytes: int = 1_000, fail: str | None = None):
        self.queries = 0
        self.dry_runs = 0
        self.bytes = per_unit_bytes
        self.fail = fail

    def query(self, sql, job_config=None):
        if job_config is not None and job_config.dry_run:
            self.dry_runs += 1
            return _Job([], self.bytes, True)
        self.queries += 1
        if self.fail:
            raise RuntimeError(self.fail)
        rows = [
            (1, "WatchEvent", datetime(2020, 1, 2, 3), 10),
            # chunks hold disjoint days, so each call returns its own day's pushes (plus a
            # within-chunk duplicate that must be collapsed)
            (100 * self.queries + 2, "PushEvent", datetime(2020, 1, 1 + self.queries, 4), 10),
            (100 * self.queries + 3, "PushEvent", datetime(2020, 1, 1 + self.queries, 5), 10),
            (100 * self.queries + 3, "PushEvent", datetime(2020, 1, 1 + self.queries, 5), 10),
        ]
        return _Job([_batch(rows)], self.bytes, False)


@pytest.fixture(autouse=True)
def _no_bqs(monkeypatch):
    import google.cloud.bigquery_storage as bqs

    def boom(*a, **k):
        raise RuntimeError("no ADC in tests")

    monkeypatch.setattr(bqs, "BigQueryReadClient", boom)


@pytest.fixture
def cfg(write_config, tmp_path: Path) -> Config:
    def mutate(d: dict) -> None:
        d["lake"]["local_root"] = str(tmp_path / "data" / "lake")
        d["bigquery"]["monthly_budget_bytes"] = 10_000

    return load_config(write_config(mutate))


def test_units_are_week_chunks_newest_first() -> None:
    units = R.make_units(date(2020, 1, 1), date(2020, 1, 31), "spine")
    assert [u.start for u in units][0] == "2020-01-29"
    assert units[0].end == "2020-01-31" and len(units) == 5
    assert all(date.fromisoformat(u.end).month == 1 for u in units)


def test_manifest_running_unit_resets_to_todo(tmp_path: Path) -> None:
    p = tmp_path / "m.json"
    m = R.Manifest(p)
    u = R.Unit("2020-01", "2020-01-01", "2020-01-07", "spine", status="running")
    m.add([u])
    m.save()
    assert R.Manifest(p).units[u.key].status == "todo"
    assert json.loads(p.read_text())["units"][0]["status"] == "running"


def test_run_finalizes_month_and_second_run_queries_nothing(cfg: Config, tmp_path: Path) -> None:
    client = FakeClient()
    mp = tmp_path / "m.json"
    st = R.run_backfill(
        cfg, date(2020, 1, 1), date(2020, 1, 31), manifest_path=mp, client=client, workers=1
    )
    assert st["done"] == 5 and st["failed"] == 0 and not st["stopped_for_quota"]
    assert json.loads(mp.read_text())["finalized"] == {"2020-01": "spine"}
    ev = layout.bq_file("WatchEvent", 2020, 1, cfg)
    assert ev.exists()
    con = duckdb.connect()
    # the same 3 ids come back from each of the 5 chunks: deduped to one row each
    assert con.execute(f"select count(*) from '{ev}'").fetchone() == (1,)
    assert con.execute(f"select detail_level, source from '{ev}'").fetchone() == (0, "bq")
    push = layout.bq_file("PushEvent", 2020, 1, cfg)
    assert con.execute(f"select sum(n_pushes) from '{push}'").fetchone() == (10,)
    assert not (layout.staging_dir(cfg) / "bq").exists() or not any(
        (layout.staging_dir(cfg) / "bq").rglob("*.parquet")
    )
    before = client.queries
    st2 = R.run_backfill(
        cfg, date(2020, 1, 1), date(2020, 1, 31), manifest_path=mp, client=client, workers=1
    )
    assert st2["todo"] == 0 and client.queries == before


def test_quota_stop_is_clean(cfg: Config, tmp_path: Path) -> None:
    client = FakeClient(per_unit_bytes=4_000)  # budget 10_000 => 2 units fit
    mp = tmp_path / "m.json"
    st = R.run_backfill(
        cfg, date(2020, 1, 1), date(2020, 1, 31), manifest_path=mp, client=client, workers=1
    )
    assert st["done"] == 2 and st["stopped_for_quota"]
    m = R.Manifest(mp)
    assert sorted(u.status for u in m.units.values()) == ["done", "done", "todo", "todo", "todo"]
    assert m.finalized == {}


def test_error_marks_failed_after_one_retry(cfg: Config, tmp_path: Path) -> None:
    client = FakeClient(fail="boom")
    st = R.run_backfill(
        cfg,
        date(2020, 1, 1),
        date(2020, 1, 7),
        manifest_path=tmp_path / "m.json",
        client=client,
        workers=1,
    )
    assert st["failed"] == 1 and client.queries == 2


def test_dry_reports_estimate_without_queries(cfg: Config, tmp_path: Path) -> None:
    client = FakeClient(per_unit_bytes=500)
    st = R.run_backfill(
        cfg,
        date(2020, 1, 1),
        date(2020, 1, 31),
        manifest_path=tmp_path / "m.json",
        client=client,
        dry=True,
        workers=1,
    )
    assert st["estimated_bytes"] == 2_500 and client.queries == 0


def test_full_mode_sets_detail_level_and_upgrade_replaces_spine(
    cfg: Config, tmp_path: Path
) -> None:
    mp = tmp_path / "m.json"
    client = FakeClient()
    R.run_backfill(
        cfg, date(2020, 1, 1), date(2020, 1, 7), manifest_path=mp, client=client, workers=1
    )
    R.run_backfill(
        cfg,
        date(2020, 1, 1),
        date(2020, 1, 7),
        mode="full",
        manifest_path=mp,
        client=client,
        workers=1,
    )
    ev = layout.bq_file("WatchEvent", 2020, 1, cfg)
    assert duckdb.connect().execute(f"select detail_level from '{ev}'").fetchone() == (1,)
    assert json.loads(mp.read_text())["finalized"] == {"2020-01": "full"}
    assert R._needs_finalize(R.Manifest(mp), "2020-01", "spine") is False
