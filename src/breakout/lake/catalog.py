"""Catalog of lake files: one row per Parquet file, built from footers (no data scans).

``catalog.parquet`` sits at the root of the events repo and is committed together with every data
change, so it always describes exactly the files that exist remotely. Paths are relative to the
lake root and identical locally and on Hugging Face.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable
from datetime import UTC, date, datetime, time
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from breakout.lake.hf import ShaCache, sha256_file
from breakout.schema import EVENTS_SCHEMA, PUSH_DAILY_SCHEMA, SCHEMA_VERSION

KV_SCHEMA_VERSION = b"breakout.schema_version"
FILE_RE = re.compile(r"^(bq|day|month)-(\d{6}|\d{4}-\d{2}-\d{2})(-part\d{3})?\.parquet$")
PUSH_TABLE = "push_daily"
EVENTS_TABLE = "events"

CATALOG_SCHEMA = pa.schema(
    [
        pa.field("path", pa.string(), nullable=False),
        pa.field("table", pa.string(), nullable=False),
        pa.field("event_type", pa.string()),
        pa.field("year", pa.int32(), nullable=False),
        pa.field("month", pa.int32(), nullable=False),
        pa.field("kind", pa.string(), nullable=False),
        pa.field("day", pa.date32()),
        pa.field("rows", pa.int64(), nullable=False),
        pa.field("bytes", pa.int64(), nullable=False),
        pa.field("sha256", pa.string(), nullable=False),
        pa.field("min_created_at", pa.timestamp("us")),
        pa.field("max_created_at", pa.timestamp("us")),
        pa.field("detail_level_min", pa.int32()),
        pa.field("detail_level_max", pa.int32()),
        pa.field("source_min", pa.string()),
        pa.field("source_max", pa.string()),
        pa.field("schema_version", pa.int32(), nullable=False),
    ]
)


def lake_files(root: Path, tables: Iterable[str] = (EVENTS_TABLE, PUSH_TABLE)) -> list[Path]:
    """Publishable data files under ``root``: ``{bq,day,month}-*.parquet`` only (never
    .tmp/.partial, spill or staging files), in a deterministic month order."""
    pats = []
    if EVENTS_TABLE in tables:
        pats.append("events/event_type=*/year=*/month=*/*.parquet")
    if PUSH_TABLE in tables:
        pats.append("push_daily/year=*/month=*/*.parquet")
    out: list[Path] = []
    for pat in pats:
        out.extend(p for p in root.glob(pat) if FILE_RE.match(p.name))

    # month order first (year=, month= dirs sit at the same depth in both tables)
    return sorted(
        out,
        key=lambda p: (p.parent.parent.name, p.parent.name, p.relative_to(root).as_posix()),
    )


def parse_path(rel: str) -> dict:
    """Decompose a repo-relative path into catalog key fields."""
    parts = rel.split("/")
    name = parts[-1]
    m = FILE_RE.match(name)
    if m is None:
        raise ValueError(f"not a lake data file: {rel}")
    kind, stamp = m.group(1), m.group(2)
    year = int(parts[-3].split("=")[1])
    month = int(parts[-2].split("=")[1])
    table = PUSH_TABLE if parts[0] == PUSH_TABLE else EVENTS_TABLE
    etype = parts[1].split("=")[1] if table == EVENTS_TABLE else None
    day = date.fromisoformat(stamp) if kind == "day" else None
    return {
        "table": table,
        "event_type": etype,
        "year": year,
        "month": month,
        "kind": kind,
        "day": day,
    }


def _stat_range(md: pq.FileMetaData, col: str):
    """(min, max) of a column from row-group statistics, or (None, None) when unavailable."""
    idx = None
    for i in range(md.num_columns):
        if md.schema.column(i).path == col:
            idx = i
            break
    if idx is None:
        return None, None
    lo = hi = None
    for rg in range(md.num_row_groups):
        st = md.row_group(rg).column(idx).statistics
        if st is None or not st.has_min_max:
            return None, None
        lo = st.min if lo is None or st.min < lo else lo
        hi = st.max if hi is None or st.max > hi else hi
    return lo, hi


def _schema_version(pf: pq.ParquetFile, table: str) -> int:
    kv = pf.schema_arrow.metadata or {}
    if KV_SCHEMA_VERSION in kv:
        try:
            return int(kv[KV_SCHEMA_VERSION])
        except ValueError:
            return 0
    want = EVENTS_SCHEMA if table == EVENTS_TABLE else PUSH_DAILY_SCHEMA
    have = pf.schema_arrow
    same = have.names == want.names and all(
        have.field(n).type == want.field(n).type for n in want.names
    )
    return SCHEMA_VERSION if same else 0


def _ts(v) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.replace(tzinfo=None)
    if isinstance(v, date):
        return datetime.combine(v, time.min)
    return None


def catalog_row(root: Path, file: Path, cache: ShaCache | None = None) -> dict:
    rel = file.relative_to(root).as_posix()
    info = parse_path(rel)
    pf = pq.ParquetFile(file)
    md = pf.metadata
    ts_col = "day" if info["table"] == PUSH_TABLE else "created_at"
    lo, hi = _stat_range(md, ts_col)
    dl_lo, dl_hi = _stat_range(md, "detail_level")
    s_lo, s_hi = _stat_range(md, "source")
    if info["table"] == PUSH_TABLE and hi is not None:
        # `day` is a DATE; its max is the start of the last day
        hi = _ts(hi)
        lo = _ts(lo)
    return {
        "path": rel,
        **info,
        "rows": md.num_rows,
        "bytes": file.stat().st_size,
        "sha256": cache.get(rel, file) if cache else sha256_file(file),
        "min_created_at": _ts(lo),
        "max_created_at": _ts(hi),
        "detail_level_min": None if dl_lo is None else int(dl_lo),
        "detail_level_max": None if dl_hi is None else int(dl_hi),
        "source_min": s_lo,
        "source_max": s_hi,
        "schema_version": _schema_version(pf, info["table"]),
    }


def build_catalog(
    root: Path,
    *,
    tables: Iterable[str] = (EVENTS_TABLE, PUSH_TABLE),
    cache: ShaCache | None = None,
    files: Iterable[Path] | None = None,
    workers: int = 4,
) -> pa.Table:
    """Catalog rows for the local lake (or only ``files``), reading Parquet footers only."""
    from concurrent.futures import ThreadPoolExecutor

    selected = list(files) if files is not None else lake_files(root, tuple(tables))
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        rows = list(pool.map(lambda f: catalog_row(root, f, cache), selected))
    rows.sort(key=lambda r: r["path"])
    return pa.Table.from_pylist(rows, schema=CATALOG_SCHEMA)


def write_catalog(table: pa.Table, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    pq.write_table(table.cast(CATALOG_SCHEMA), tmp, compression="zstd")
    os.replace(tmp, dest)
    return dest


def read_catalog(path: Path) -> pa.Table:
    return pq.read_table(path).cast(CATALOG_SCHEMA)


def merge_catalogs(
    base: pa.Table, updates: pa.Table, removed_paths: Iterable[str] = ()
) -> pa.Table:
    """``base`` with rows of ``updates`` replacing same-path rows and ``removed_paths`` dropped."""
    drop = set(removed_paths) | set(updates.column("path").to_pylist())
    rows = [r for r in base.to_pylist() if r["path"] not in drop]
    rows.extend(updates.to_pylist())
    rows.sort(key=lambda r: r["path"])
    return pa.Table.from_pylist(rows, schema=CATALOG_SCHEMA)


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    first = date(year, month, 1)
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    return first, nxt  # [first, nxt)


def select_files(
    catalog: pa.Table | list[dict],
    table: str,
    event_types: Iterable[str] | None = None,
    start_day: date | None = None,
    end_day: date | None = None,
) -> list[str]:
    """Paths needed to cover ``[start_day, end_day]`` (inclusive, either open).

    Per (event_type, month): compacted ``month`` files supersede ``bq`` and ``day`` files; without
    them the ``bq`` file(s) plus ``day`` files inside the range are used. Month-granular files are
    included whole (a month overlapping the range is needed in full).
    """
    rows = catalog.to_pylist() if isinstance(catalog, pa.Table) else list(catalog)
    wanted = set(event_types) if event_types is not None else None
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        if r["table"] != table:
            continue
        if table == EVENTS_TABLE and wanted is not None and r["event_type"] not in wanted:
            continue
        first, nxt = _month_bounds(r["year"], r["month"])
        if end_day is not None and first > end_day:
            continue
        if start_day is not None and nxt <= start_day:
            continue
        groups.setdefault((r["event_type"], r["year"], r["month"]), []).append(r)
    out: list[str] = []
    for _, rs in sorted(groups.items(), key=lambda kv: (kv[0][1], kv[0][2], str(kv[0][0]))):
        months = [r for r in rs if r["kind"] == "month"]
        if months:
            out.extend(sorted(r["path"] for r in months))
            continue
        out.extend(sorted(r["path"] for r in rs if r["kind"] == "bq"))
        for r in sorted(rs, key=lambda r: r["path"]):
            if r["kind"] != "day":
                continue
            d = r["day"]
            if (start_day is None or d >= start_day) and (end_day is None or d <= end_day):
                out.append(r["path"])
    return out


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None, microsecond=0)
