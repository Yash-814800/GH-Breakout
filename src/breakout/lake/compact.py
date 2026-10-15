"""Monthly compaction: ``day-*.parquet`` files of a finished month -> ``month-YYYYMM.parquet``.

Memory model (CLAUDE.md section 10, ADR-012): every DuckDB statement runs on a fresh connection with
``memory_limit`` and ``threads=1``, spilling to ``data/staging``. Day files are already deduplicated
per day (an event belongs to exactly one ``created_at`` day), so the month file is a sort-only pass
``ORDER BY repo_id, created_at, event_id``; ``push_daily`` is a streaming concatenation in
day order.

Order of effects for a push: write month file(s) locally -> one atomic Hub commit (add month files +
refreshed catalog, delete the day files) -> only then delete the local day files.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
from huggingface_hub import HfApi

from breakout.config import Config
from breakout.ingest import manifest as mf
from breakout.lake import catalog as cat
from breakout.lake import hf, layout, sync
from breakout.logging import get_logger
from breakout.schema import EVENTS_SCHEMA, PUSH_DAILY_SCHEMA, SCHEMA_VERSION

log = get_logger(__name__)
ROW_GROUP_SIZE = 131_072
DEFAULT_MEMORY = "1500MB"


@dataclass
class CompactResult:
    year: int
    month: int
    status: str  # compacted | noop | incomplete | not_applicable
    reason: str = ""
    written: list[Path] = field(default_factory=list)
    day_files: list[Path] = field(default_factory=list)
    removed_local: list[Path] = field(default_factory=list)
    commits: list[str] = field(default_factory=list)


def month_range(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year + (month == 12), month % 12 + 1, 1)


def month_complete(cfg: Config, year: int, month: int) -> tuple[bool, str]:
    """Complete = every hour of the month has a manifest row that is ``ok`` or ``missing`` and every
    day with at least one ``ok`` hour has its day file for every type."""
    first, nxt = month_range(year, month)
    rows = mf.HourlyManifest(layout.hourly_manifest_path(cfg)).load()
    ok_days: set[date] = set()
    start = datetime(first.year, first.month, first.day)
    for h in mf.iter_hours(start, datetime(nxt.year, nxt.month, nxt.day)):
        r = rows.get(h)
        if r is None:
            return False, f"hour {h:%Y-%m-%d %H} not in the manifest"
        if r.status not in (mf.OK, mf.MISSING):
            return False, f"hour {h:%Y-%m-%d %H} is {r.status}"
        if r.status == mf.OK:
            ok_days.add(h.date())
    types = [*cfg.events.raw_types, layout.PUSH_TYPE]
    for d in sorted(ok_days):
        for t in types:
            f = layout.day_file(t, d, cfg)
            if not f.exists():
                return False, f"missing day file {f.name} for {t}"
    return True, ""


def _day_files(cfg: Config, etype: str, year: int, month: int) -> list[Path]:
    return sorted(layout.month_dir(etype, year, month, cfg).glob("day-*.parquet"))


def _duck(memory_limit: str, spill: Path) -> duckdb.DuckDBPyConnection:
    spill.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"SET memory_limit='{memory_limit}'")
    con.execute("SET threads=1")
    con.execute("SET preserve_insertion_order=false")
    con.execute(f"SET temp_directory='{spill.as_posix()}'")
    return con


def _sorted_events(files: list[Path], dest: Path, memory_limit: str, spill: Path) -> None:
    con = _duck(memory_limit, spill)
    try:
        flist = ", ".join("'" + f.as_posix().replace("'", "''") + "'" for f in files)
        con.execute(
            f"COPY (SELECT * FROM read_parquet([{flist}], hive_partitioning=false) "
            "ORDER BY repo_id, created_at, event_id) "
            f"TO '{dest.as_posix()}' (FORMAT parquet, COMPRESSION zstd, "
            f"ROW_GROUP_SIZE {ROW_GROUP_SIZE}, "
            f"KV_METADATA {{'breakout.schema_version': '{SCHEMA_VERSION}'}})"
        )
    finally:
        con.close()


def _concat_push(files: list[Path], dest: Path) -> None:
    schema = PUSH_DAILY_SCHEMA.with_metadata({"breakout.schema_version": str(SCHEMA_VERSION)})
    with pq.ParquetWriter(dest, schema, compression="zstd") as w:
        for f in files:  # day order == (day, repo_id, actor_id) order
            pf = pq.ParquetFile(f)
            for batch in pf.iter_batches(batch_size=ROW_GROUP_SIZE):
                w.write_table(pa.Table.from_batches([batch]).cast(PUSH_DAILY_SCHEMA))


def _row_group_bytes(pf: pq.ParquetFile) -> list[int]:
    md = pf.metadata
    return [
        sum(md.row_group(i).column(j).total_compressed_size for j in range(md.num_columns))
        for i in range(md.num_row_groups)
    ]


def _split_parts(src: Path, max_bytes: int) -> list[list[int]]:
    """Greedy contiguous grouping of row groups into parts of <= max_bytes (>= 1 group each)."""
    pf = pq.ParquetFile(src)
    sizes = _row_group_bytes(pf)
    parts: list[list[int]] = [[]]
    cur = 0
    for i, s in enumerate(sizes):
        if parts[-1] and cur + s > max_bytes:
            parts.append([])
            cur = 0
        parts[-1].append(i)
        cur += s
    return parts


def _write_parts(src: Path, parts: list[list[int]], outs: list[Path]) -> None:
    pf = pq.ParquetFile(src)
    schema = pf.schema_arrow
    for groups, out in zip(parts, outs, strict=True):
        with pq.ParquetWriter(out, schema, compression="zstd") as w:
            for g in groups:
                w.write_table(pf.read_row_group(g))


def _validate(out: Path, expected_rows: int, table: str, first: date, nxt: date) -> None:
    pf = pq.ParquetFile(out)
    want = EVENTS_SCHEMA if table == cat.EVENTS_TABLE else PUSH_DAILY_SCHEMA
    got = pf.schema_arrow
    if got.names != want.names or any(got.field(n).type != want.field(n).type for n in want.names):
        raise RuntimeError(f"{out.name}: schema drift {got.names}")
    if pf.metadata.num_rows != expected_rows:
        raise RuntimeError(f"{out.name}: {pf.metadata.num_rows} rows, expected {expected_rows}")
    ts_col = "day" if table == cat.PUSH_TABLE else "created_at"
    lo, hi = cat._stat_range(pf.metadata, ts_col)
    if lo is not None:
        lo_d = lo.date() if isinstance(lo, datetime) else lo
        hi_d = hi.date() if isinstance(hi, datetime) else hi
        if lo_d < first or hi_d >= nxt:
            raise RuntimeError(f"{out.name}: rows span {lo_d}..{hi_d} outside {first}..{nxt}")


def build_month_files(
    cfg: Config,
    etype: str,
    year: int,
    month: int,
    *,
    memory_limit: str = DEFAULT_MEMORY,
    max_file_bytes: int | None = None,
) -> tuple[list[Path], list[Path]]:
    """Write ``month-YYYYMM[-partNNN].parquet`` for one type from its day files.

    Returns (month files, day files consumed); ([], []) when the type has no day files.
    Stale ``month-`` files of this month that are not part of the new set are removed (a changed
    part count after a re-run), but only after the new files are in place.
    """
    days = _day_files(cfg, etype, year, month)
    if not days:
        return [], []
    first, nxt = month_range(year, month)
    table = cat.PUSH_TABLE if etype == layout.PUSH_TYPE else cat.EVENTS_TABLE
    expected = sum(pq.ParquetFile(f).metadata.num_rows for f in days)
    mdir = layout.month_dir(etype, year, month, cfg)
    stem = f"month-{year:04d}{month:02d}"
    full = mdir / f"{stem}.parquet.tmp"
    full.unlink(missing_ok=True)
    if table == cat.PUSH_TABLE:
        _concat_push(days, full)
    else:
        _sorted_events(days, full, memory_limit, layout.staging_dir(cfg) / "duckdb_tmp")
    _validate(full, expected, table, first, nxt)
    limit = max_file_bytes or cfg.lake.max_file_mb * 1024 * 1024
    parts = _split_parts(full, limit) if full.stat().st_size > limit else [[]]
    if len(parts) == 1:
        finals = [mdir / f"{stem}.parquet"]
        os.replace(full, finals[0])
    else:
        finals = [mdir / f"{stem}-part{i + 1:03d}.parquet" for i in range(len(parts))]
        tmps = [p.with_name(p.name + ".tmp") for p in finals]
        _write_parts(full, parts, tmps)
        full.unlink()
        for t, f in zip(tmps, finals, strict=True):
            os.replace(t, f)
    for stale in mdir.glob(f"{stem}*.parquet"):
        if stale not in finals:
            stale.unlink()
    return finals, days


def compact_month(
    cfg: Config,
    year: int,
    month: int,
    *,
    api: HfApi | None = None,
    push: bool = True,
    delete_local_days: bool = True,
    memory_limit: str = DEFAULT_MEMORY,
    max_file_bytes: int | None = None,
    force: bool = False,
    cache: hf.ShaCache | None = None,
) -> CompactResult:
    """Compact one month. Idempotent: a month without day files left locally is a no-op."""
    res = CompactResult(year, month, "noop")
    first, _ = month_range(year, month)
    cutover = cfg.history.cutover_date
    if cutover is not None and first < cutover.replace(day=1):
        res.status, res.reason = "not_applicable", "month is before the hourly era (bq files)"
        return res
    types = [*cfg.events.raw_types, layout.PUSH_TYPE]
    if not any(_day_files(cfg, t, year, month) for t in types):
        res.reason = "no local day files"
        return res
    ok, why = month_complete(cfg, year, month)
    if not ok and not force:
        res.status, res.reason = "incomplete", why
        return res
    for t in types:
        out, days = build_month_files(
            cfg, t, year, month, memory_limit=memory_limit, max_file_bytes=max_file_bytes
        )
        res.written += out
        res.day_files += days
    res.status = "compacted"
    log.info(
        "compacted %04d-%02d: %d day files -> %d month files",
        year,
        month,
        len(res.day_files),
        len(res.written),
    )
    if push:
        api = api or hf.get_api()
        root = layout.lake_root(cfg)
        deletes = _remote_deletes(api, cfg, year, month, res.written, root)
        res.commits = sync.push_files(
            api,
            cfg,
            root,
            res.written,
            f"compact {year:04d}-{month:02d}: {len(res.day_files)} day files -> month files",
            deletes=deletes,
            cache=cache,
        )
    if push and delete_local_days:
        for f in res.day_files:
            f.unlink(missing_ok=True)
            res.removed_local.append(f)
    return res


def _remote_deletes(
    api: HfApi, cfg: Config, year: int, month: int, new_files: list[Path], root: Path
) -> list[str]:
    """Remote paths of this month made redundant: its day files and any stale month parts."""
    remote, _ = sync.fetch_remote_catalog(api, cfg)
    keep = {f.relative_to(root).as_posix() for f in new_files}
    out = []
    for r in remote.to_pylist():
        if r["year"] != year or r["month"] != month or r["path"] in keep:
            continue
        if r["kind"] in ("day", "month"):
            out.append(r["path"])
    return out


def iter_months(first: date, last: date) -> Iterator[tuple[int, int]]:
    y, m = first.year, first.month
    while (y, m) <= (last.year, last.month):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
