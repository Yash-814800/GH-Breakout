"""One month of the hourly era, end to end, for the GitHub Actions matrix (ADR-011/014).

ingest the month's days (Phase 1 parser) -> compact to month files (memory-bounded) -> push the
month files + catalog + this month's manifest fragment to the events repo -> remove staging.

Resumability comes from the remote catalog: a month that already has ``month-`` files on the Hub is
skipped. Each job writes its own manifest fragment ``manifests/hourly/hourly-YYYYMM.parquet`` so
concurrent jobs never write the same remote file (``lake pull --manifests`` merges them locally).
A month that is not complete yet (the running month) is pushed as ``day-`` files instead.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from huggingface_hub import HfApi

from breakout.config import Config
from breakout.ingest.backfill import last_complete_day
from breakout.ingest.day import DaySummary, clean_staging, ingest_day
from breakout.lake import compact, hf, layout, sync
from breakout.logging import get_logger

log = get_logger(__name__)


@dataclass
class MonthRun:
    year: int
    month: int
    status: str  # skipped | pushed_month | pushed_days | nothing
    days: int = 0
    files: int = 0
    commits: int = 0
    detail: str = ""


def month_days(year: int, month: int, last: date) -> list[date]:
    first, nxt = compact.month_range(year, month)
    d, out = first, []
    while d < nxt and d <= last:
        out.append(d)
        d += timedelta(days=1)
    return out


def remote_has_month(remote: object, year: int, month: int) -> bool:
    rows = remote.to_pylist()  # type: ignore[attr-defined]
    return any(r["year"] == year and r["month"] == month and r["kind"] == "month" for r in rows)


def run_month(
    cfg: Config,
    year: int,
    month: int,
    *,
    api: HfApi | None = None,
    workers: int = 2,
    memory_limit: str = compact.DEFAULT_MEMORY,
    now: datetime | None = None,
    ingest: Callable[..., DaySummary] = ingest_day,
    keep_staging: bool = False,
) -> MonthRun:
    api = api or hf.get_api()
    remote, _ = sync.fetch_remote_catalog(api, cfg)
    if remote_has_month(remote, year, month):
        return MonthRun(year, month, "skipped", detail="month files already on the Hub")
    last = last_complete_day(cfg, now)
    days = month_days(year, month, last)
    if not days:
        return MonthRun(year, month, "nothing", detail="no complete day yet")
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        list(
            pool.map(
                lambda d: ingest(d, cfg=cfg, keep_raw=False, hour_workers=1, now=now),
                days,
            )
        )
    root = layout.lake_root(cfg)
    res = compact.compact_month(cfg, year, month, push=False, memory_limit=memory_limit, cache=None)
    if res.status == "compacted":
        files = res.written
        status = "pushed_month"
    else:
        # month still running (or hours pending): publish the day files, compact later
        files = sorted(
            f
            for t in [*cfg.events.raw_types, layout.PUSH_TYPE]
            for f in layout.month_dir(t, year, month, cfg).glob("day-*.parquet")
        )
        status = "pushed_days"
    fragment = _manifest_fragment(cfg, year, month)
    extra = [hf.UploadItem(fragment, f"manifests/hourly/hourly-{year:04d}{month:02d}.parquet")]
    deletes = (
        compact._remote_deletes(api, cfg, year, month, files, root)
        if status == "pushed_month"
        else []
    )
    commits = sync.push_files(
        api,
        cfg,
        root,
        files,
        f"hourly backfill {year:04d}-{month:02d} ({status.removeprefix('pushed_')})",
        deletes=deletes,
        extra=extra,
    )
    if res.status == "compacted":
        # all of it is remote now: day files are redundant locally
        for f in res.day_files:
            f.unlink(missing_ok=True)
    if not keep_staging:
        for d in days:
            clean_staging(d, cfg)
        shutil.rmtree(layout.staging_dir(cfg) / "duckdb_tmp", ignore_errors=True)
    return MonthRun(year, month, status, len(days), len(files), len(commits), res.reason)


def _manifest_fragment(cfg: Config, year: int, month: int):
    import pyarrow as pa
    import pyarrow.parquet as pq

    from breakout.ingest.manifest import MANIFEST_SCHEMA, HourlyManifest

    first, nxt = compact.month_range(year, month)
    rows = [
        r
        for h, r in HourlyManifest(layout.hourly_manifest_path(cfg)).load().items()
        if first <= h.date() < nxt
    ]
    from dataclasses import asdict

    table = pa.Table.from_pylist(
        [asdict(r) for r in sorted(rows, key=lambda r: r.hour_ts)], schema=MANIFEST_SCHEMA
    )
    dest = layout.manifests_dir(cfg) / "hourly" / f"hourly-{year:04d}{month:02d}.parquet"
    dest.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, dest, compression="zstd")
    return dest


def run_gap_days(
    cfg: Config,
    *,
    api: HfApi | None = None,
    workers: int = 2,
    ingest: Callable[..., DaySummary] = ingest_day,
    now: datetime | None = None,
) -> MonthRun:
    """Ingest ``history.hourly_gap_days`` (days BigQuery lacks) and push them as ``day-`` files.

    They sit next to the ``bq`` file of their month, which is allowed only for these days.
    """
    from concurrent.futures import ThreadPoolExecutor

    api = api or hf.get_api()
    days = sorted(cfg.history.hourly_gap_days)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        list(pool.map(lambda d: ingest(d, cfg=cfg, keep_raw=False, hour_workers=1, now=now), days))
    root = layout.lake_root(cfg)
    files = sorted(
        f
        for d in days
        for t in [*cfg.events.raw_types, layout.PUSH_TYPE]
        if (f := layout.day_file(t, d, cfg)).exists()
    )
    import pyarrow as pa
    import pyarrow.parquet as pq

    from breakout.ingest.manifest import MANIFEST_SCHEMA, HourlyManifest

    rows = [
        r
        for h, r in HourlyManifest(layout.hourly_manifest_path(cfg)).load().items()
        if h.date() in set(days)
    ]
    from dataclasses import asdict

    frag = layout.manifests_dir(cfg) / "hourly" / "hourly-gap-days.parquet"
    frag.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        pa.Table.from_pylist(
            [asdict(r) for r in sorted(rows, key=lambda r: r.hour_ts)], schema=MANIFEST_SCHEMA
        ),
        frag,
        compression="zstd",
    )
    commits = sync.push_files(
        api,
        cfg,
        root,
        files,
        f"hourly backfill: {len(days)} gap day(s) missing from BigQuery",
        extra=[hf.UploadItem(frag, "manifests/hourly/hourly-gap-days.parquet")],
    )
    for d in days:
        clean_staging(d, cfg)
    return MonthRun(0, 0, "pushed_days", len(days), len(files), len(commits))
