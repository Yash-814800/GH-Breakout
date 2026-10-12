"""Ingest one UTC day: 24 hourly files -> staged per-hour parquet -> day files in the lake.

Design notes
- Staging (``data/staging/{day}/``) is the source of truth for building day files. A day file is
  a pure function of the staged hour files of that day plus ``spill-from-*`` files holding
  boundary events that other days' hourly files contained.
- An hour marked ``ok`` in the manifest whose staged file is missing is re-ingested, so a day is
  never built from a partial set of staged hours by accident.
- Day files are rewritten only when at least one hour was (re)processed in this call, so running
  the command twice leaves the lake untouched.
"""

from __future__ import annotations

import os
import shutil
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from breakout.config import Config, get_config
from breakout.duck import connect
from breakout.ingest import manifest as mf
from breakout.ingest.gharchive import DownloadResult, download_from_sources
from breakout.ingest.parse import PUSH_TYPE, parse_hour_file
from breakout.lake import layout
from breakout.logging import get_logger
from breakout.schema import (
    EVENTS_SCHEMA,
    PARSER_VERSION,
    PUSH_DAILY_SCHEMA,
    PUSH_ROWS_SCHEMA,
    SOURCE_HOURLY,
    SOURCE_OPENDIGGER,
)

log = get_logger(__name__)

# (hour, dest_dir, sources in priority order) -> DownloadResult
Downloader = Callable[[datetime, Path, list], DownloadResult]
ROW_GROUP_SIZE = 131_072


@dataclass
class DaySummary:
    day: date
    hours_processed: int = 0
    hours_skipped: int = 0
    hours_ok: int = 0
    missing_hours: list[int] = field(default_factory=list)
    pending_hours: list[int] = field(default_factory=list)
    error_hours: list[int] = field(default_factory=list)
    rows_per_type: Counter[str] = field(default_factory=Counter)
    files_written: list[Path] = field(default_factory=list)


def _day_staging(cfg: Config, day: date) -> Path:
    return layout.staging_dir(cfg) / day.isoformat()


def _hour_paths(cfg: Config, day: date, hour: int) -> tuple[Path, Path]:
    d = _day_staging(cfg, day)
    return d / f"hour={hour}.events.parquet", d / f"hour={hour}.push.parquet"


def _atomic_write_table(table: pa.Table, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    pq.write_table(table, tmp, compression="zstd")
    os.replace(tmp, dest)


def _process_hour(
    ts: datetime,
    *,
    cfg: Config,
    now: datetime,
    downloader: Downloader,
    keep_raw: bool,
) -> mf.ManifestRow:
    day = ts.date()
    raw_dir = layout.raw_dir(cfg) / day.isoformat()
    res = downloader(ts, raw_dir, cfg.ingest.sources_for(day))
    stamp = now.replace(tzinfo=None, microsecond=0)
    if res.status == "missing":
        status = mf.status_for_404(ts, now.replace(tzinfo=None), cfg.daily.late_hour_retry_days)
        return mf.ManifestRow(
            ts, status, 0, 0, None, res.attempts, stamp, PARSER_VERSION, res.source_host
        )
    if res.status != "ok" or res.path is None:
        return mf.ManifestRow(
            ts,
            mf.ERROR,
            None,
            res.size_bytes or None,
            res.sha256,
            res.attempts,
            stamp,
            PARSER_VERSION,
            res.source_host,
            res.expected_events,
            res.expected_sha256,
            res.integrity,
        )
    try:
        parsed = parse_hour_file(
            res.path,
            ts,
            raw_types=cfg.events.raw_types,
            aggregated_types=cfg.events.aggregated_types,
            source=SOURCE_OPENDIGGER if res.source_host == "opendigger" else SOURCE_HOURLY,
            ingested_at=now,
        )
        ev_path, push_path = _hour_paths(cfg, day, ts.hour)
        _atomic_write_table(parsed.events, ev_path)
        _atomic_write_table(parsed.push_rows, push_path)
    except Exception as exc:  # parse failure must not abort the day; retried next run
        log.exception("parse failed for %s: %s", ts, exc)
        return mf.ManifestRow(
            ts,
            mf.ERROR,
            None,
            res.size_bytes,
            res.sha256,
            res.attempts,
            stamp,
            PARSER_VERSION,
            res.source_host,
        )
    finally:
        if not keep_raw and res.path is not None:
            res.path.unlink(missing_ok=True)
    s = parsed.stats
    log.info(
        "%s: %d rows (%d lines, %d bad json, %d bad ids, %d dup)",
        ts.isoformat(timespec="hours"),
        s.rows_kept,
        s.lines_read,
        s.bad_json_lines,
        s.bad_ids,
        s.duplicates,
    )
    if res.expected_events is not None and res.expected_events != s.lines_read:
        log.warning(
            "%s: manifest says %d events, file has %d lines (%s)",
            ts.isoformat(timespec="hours"),
            res.expected_events,
            s.lines_read,
            res.source_host,
        )
    return mf.ManifestRow(
        ts,
        mf.OK,
        s.rows_kept,
        res.size_bytes,
        res.sha256,
        res.attempts,
        stamp,
        PARSER_VERSION,
        res.source_host,
        res.expected_events,
        res.expected_sha256,
        res.integrity,
    )


def _write_spills(cfg: Config, day: date) -> list[date]:
    """Move boundary events (created_at date != day) of staged hours into their own day's
    ``spill-from-{day}`` files. Returns the target days written."""
    d = _day_staging(cfg, day)
    ev_files = sorted(d.glob("hour=*.events.parquet"))
    push_files = sorted(d.glob("hour=*.push.parquet"))
    targets: set[date] = set()
    con = connect()
    try:
        con.execute("SET preserve_insertion_order = true")
        for kind, files, schema in (
            ("events", ev_files, EVENTS_SCHEMA),
            ("push", push_files, PUSH_ROWS_SCHEMA),
        ):
            if not files:
                continue
            rows = con.execute(
                "SELECT DISTINCT CAST(created_at AS DATE) FROM read_parquet(?) "
                "WHERE CAST(created_at AS DATE) <> ?",
                [[str(f) for f in files], day],
            ).fetchall()
            for (other,) in rows:
                table = con.execute(
                    "SELECT * FROM read_parquet(?) WHERE CAST(created_at AS DATE) = ? "
                    "ORDER BY event_id",
                    [[str(f) for f in files], other],
                ).to_arrow_table()
                dest = _day_staging(cfg, other) / f"spill-from-{day.isoformat()}.{kind}.parquet"
                _atomic_write_table(table.cast(schema), dest)
                targets.add(other)
    finally:
        con.close()
    return sorted(targets)


def _copy_sorted(con, select_sql: str, params: list, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.unlink(missing_ok=True)
    con.execute(
        f"COPY ({select_sql}) TO '{tmp.as_posix()}' "
        f"(FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE {ROW_GROUP_SIZE})",
        params,
    )
    os.replace(tmp, dest)


def build_day_files(cfg: Config, day: date, now: datetime) -> tuple[list[Path], Counter[str]]:
    """Build one parquet per raw event type + push_daily for ``day`` from its staging dir."""
    d = _day_staging(cfg, day)
    ev_files = sorted([*d.glob("hour=*.events.parquet"), *d.glob("spill-from-*.events.parquet")])
    push_files = sorted([*d.glob("hour=*.push.parquet"), *d.glob("spill-from-*.push.parquet")])
    written: list[Path] = []
    counts: Counter[str] = Counter()
    if not ev_files and not push_files:
        return written, counts
    stamp = now.replace(tzinfo=None, microsecond=0)
    con = connect()
    try:
        con.execute("SET preserve_insertion_order = true")
        if ev_files:
            flist = [str(f) for f in ev_files]
            for etype in cfg.events.raw_types:
                dest = layout.day_file(etype, day, cfg)
                sql = (
                    "SELECT * FROM ("
                    "  SELECT DISTINCT ON (event_id) * FROM read_parquet(?) "
                    "  WHERE event_type = ? AND CAST(created_at AS DATE) = ? "
                    "  ORDER BY event_id, ingested_at DESC"
                    ") ORDER BY repo_id, created_at, event_id"
                )
                _copy_sorted(con, sql, [flist, etype, day], dest)
                n = con.execute(
                    "SELECT count(*) FROM read_parquet(?)", [dest.as_posix()]
                ).fetchone()
                counts[etype] = n[0] if n else 0
                written.append(dest)
        if push_files:
            flist = [str(f) for f in push_files]
            dest = layout.day_file(PUSH_TYPE, day, cfg)
            sql = (
                "SELECT repo_id, actor_id, day, CAST(count(*) AS INTEGER) AS n_pushes, "
                "arg_max(repo_name, event_id) AS repo_name, "
                "CASE WHEN bool_or(source = ?) THEN ? ELSE ? END AS source, "
                "CAST(? AS TIMESTAMP) AS ingested_at FROM ("
                "  SELECT DISTINCT ON (event_id) event_id, repo_id, actor_id, repo_name, source, "
                "         CAST(created_at AS DATE) AS day "
                "  FROM read_parquet(?) WHERE CAST(created_at AS DATE) = ? ORDER BY event_id"
                ") GROUP BY repo_id, actor_id, day ORDER BY repo_id, actor_id, day"
            )
            _copy_sorted(
                con,
                sql,
                [SOURCE_OPENDIGGER, SOURCE_OPENDIGGER, SOURCE_HOURLY, stamp, flist, day],
                dest,
            )
            # keep the schema contract honest
            t = pq.read_table(dest)
            if t.schema.names != PUSH_DAILY_SCHEMA.names:
                raise RuntimeError(f"push_daily schema drift: {t.schema.names}")
            counts[PUSH_TYPE] = t.num_rows
            written.append(dest)
    finally:
        con.close()
    return written, counts


def ingest_day(
    day: date,
    *,
    force: bool = False,
    keep_raw: bool = False,
    cfg: Config | None = None,
    now: datetime | None = None,
    downloader: Downloader | None = None,
    hour_workers: int = 2,
    only_hours: set[int] | None = None,
) -> DaySummary:
    cfg = cfg or get_config()
    now = (now or datetime.now(UTC)).replace(tzinfo=None)
    dl: Downloader = downloader or download_from_sources
    summary = DaySummary(day)
    manifest = mf.HourlyManifest(layout.hourly_manifest_path(cfg))
    start = datetime(day.year, day.month, day.day)
    end = start + timedelta(days=1)

    todo = manifest.hours_needing_work(
        start,
        end,
        now,
        parser_version=PARSER_VERSION,
        min_hour_lag=cfg.daily.min_hour_lag,
        late_hour_retry_days=cfg.daily.late_hour_retry_days,
        force=force,
        preferred_host=lambda h: (
            srcs[0].name if (srcs := cfg.ingest.sources_for(h.date())) else None
        ),
    )
    if only_hours is not None:
        todo = [h for h in todo if h.hour in only_hours]
    # self-heal: an 'ok' hour whose staged file vanished must be redone before building
    rows = manifest.load()
    todo_set = set(todo)
    for h in mf.iter_hours(start, end):
        r = rows.get(h)
        if (
            r is not None
            and r.status == mf.OK
            and r.parser_version == PARSER_VERSION
            and h not in todo_set
            and (only_hours is None or h.hour in only_hours)
            and not _hour_paths(cfg, day, h.hour)[0].exists()
            and h + timedelta(hours=1 + cfg.daily.min_hour_lag) <= now
        ):
            todo.append(h)
    todo = sorted(set(todo))
    summary.hours_skipped = (24 if only_hours is None else len(only_hours)) - len(todo)

    results: list[mf.ManifestRow] = []
    try:
        with ThreadPoolExecutor(max_workers=max(1, hour_workers)) as pool:
            futures = [
                pool.submit(_process_hour, h, cfg=cfg, now=now, downloader=dl, keep_raw=keep_raw)
                for h in todo
            ]
            for fut in futures:
                results.append(fut.result())
    finally:
        manifest.upsert(results)
    summary.hours_processed = len(results)

    for r in results:
        if r.status == mf.MISSING:
            summary.missing_hours.append(r.hour_ts.hour)
        elif r.status == mf.PENDING:
            summary.pending_hours.append(r.hour_ts.hour)
        elif r.status == mf.ERROR:
            summary.error_hours.append(r.hour_ts.hour)

    ok_hours = sum(
        1 for r in manifest.load().values() if r.status == mf.OK and r.hour_ts.date() == day
    )
    summary.hours_ok = ok_hours

    processed_ok = any(r.status == mf.OK for r in results)
    if processed_ok:
        spill_targets = _write_spills(cfg, day)
        files, counts = build_day_files(cfg, day, now)
        summary.files_written.extend(files)
        summary.rows_per_type.update(counts)
        for other in spill_targets:
            # rebuild a neighbouring day only when it is fully staged (all ok hours present)
            other_dir = _day_staging(cfg, other)
            if len(list(other_dir.glob("hour=*.events.parquet"))) == 24 or (
                layout.day_file(cfg.events.raw_types[0], other, cfg).exists()
                and list(other_dir.glob("hour=*.events.parquet"))
            ):
                build_day_files(cfg, other, now)
                log.info("rebuilt %s to include spill from %s", other, day)
            else:
                log.info("spill for %s left in staging until that day is ingested", other)
    elif not todo:
        log.info("%s: nothing to do (%d hours already ok)", day, ok_hours)
    return summary


def clean_staging(day: date, cfg: Config | None = None) -> None:
    """Remove staged files for ``day`` (the day file stays; hours will be re-ingested if needed)."""
    shutil.rmtree(_day_staging(cfg or get_config(), day), ignore_errors=True)
