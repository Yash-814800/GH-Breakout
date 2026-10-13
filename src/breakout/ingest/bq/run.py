"""Resumable BigQuery backfill: work units, manifest, streaming writes, month finalization.

Work unit = (up to 7 days inside one month, mode). Billing is by bytes scanned, so each unit is
dry-run first and skipped (cleanly) when it would exceed the monthly budget. The manifest records
every unit; a unit is either ``done`` with its staged chunk files in place or not done.
Only this package imports ``google.cloud``.
"""

from __future__ import annotations

import json
import os
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from breakout.config import Config
from breakout.ingest.bq import sql as Q
from breakout.ingest.bq.survey import month_bounds
from breakout.lake import layout
from breakout.logging import get_logger
from breakout.schema import EVENTS_SCHEMA, SOURCE_BQ

log = get_logger(__name__)

CHUNK_DAYS = 7
PUSH = "PushEvent"
_LOCK = threading.Lock()


class QuotaExhausted(Exception):
    pass


@dataclass
class Unit:
    month: str
    start: str
    end: str
    mode: str
    status: str = "todo"  # todo | running | done | failed
    bytes_billed: int = 0
    rows_by_type: dict[str, int] = field(default_factory=dict)
    started_at: str | None = None
    finished_at: str | None = None
    job_id: str | None = None
    error: str | None = None

    @property
    def key(self) -> str:
        return f"{self.start}..{self.end}:{self.mode}"


def make_units(first: date, last: date, mode: str, order: str = "newest_first") -> list[Unit]:
    units: list[Unit] = []
    for label, s, e in month_bounds(first, last):
        d = s
        while d <= e:
            c_end = min(d + timedelta(days=CHUNK_DAYS - 1), e)
            units.append(Unit(label, d.isoformat(), c_end.isoformat(), mode))
            d = c_end + timedelta(days=1)
    if order == "newest_first":
        units.sort(key=lambda u: u.start, reverse=True)
    return units


class Manifest:
    def __init__(self, path: Path):
        self.path = path
        self.units: dict[str, Unit] = {}
        self.external_spend: dict[str, int] = {}  # calendar month -> bytes spent outside units
        self.finalized: dict[str, str] = {}  # month -> mode
        if path.exists():
            raw = json.loads(path.read_text())
            self.external_spend = {k: int(v) for k, v in raw.get("external_spend", {}).items()}
            self.finalized = raw.get("finalized", {})
            for u in raw.get("units", []):
                unit = Unit(**u)
                if unit.status == "running":  # interrupted: not done
                    unit.status = "todo"
                self.units[unit.key] = unit

    def save(self) -> None:
        with _LOCK:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.name + ".tmp")
            tmp.write_text(
                json.dumps(
                    {
                        "external_spend": self.external_spend,
                        "finalized": self.finalized,
                        "units": [asdict(u) for u in self.units.values()],
                    },
                    indent=1,
                )
            )
            os.replace(tmp, self.path)

    def add(self, units: list[Unit]) -> None:
        for u in units:
            self.units.setdefault(u.key, u)

    def spent_in(self, calendar_month: str) -> int:
        total = self.external_spend.get(calendar_month, 0)
        for u in self.units.values():
            if u.finished_at and u.finished_at[:7] == calendar_month:
                total += u.bytes_billed
        return total

    def month_units(self, month: str, mode: str) -> list[Unit]:
        return [u for u in self.units.values() if u.month == month and u.mode == mode]


def _needs_finalize(manifest: Manifest, month: str, mode: str) -> bool:
    """A month is finalized once per mode; a full month is never replaced by a spine one."""
    have = manifest.finalized.get(month)
    return have is None or (have == "spine" and mode == "full")


def _staging(cfg: Config, month: str, mode: str, unit: Unit) -> Path:
    base = layout.staging_dir(cfg) / "bq" / month.replace("-", "") / mode
    return base / f"chunk-{unit.start}-{unit.end}"


_STAGE_SCHEMA = pa.schema([pa.field(f.name, f.type) for f in EVENTS_SCHEMA])  # all nullable


def _to_events_schema(batch: pa.RecordBatch, detail_level: int = 0) -> pa.Table:
    """BigQuery batch (spine+detail columns) -> slim events schema + writer columns."""
    t = pa.Table.from_batches([batch])
    n = t.num_rows
    cols: dict[str, pa.Array | pa.ChunkedArray] = {}
    for f in EVENTS_SCHEMA:
        if f.name in t.column_names:
            col = t.column(f.name)
            if pa.types.is_timestamp(f.type) and pa.types.is_timestamp(col.type):
                col = col.cast(pa.timestamp("us", tz="UTC")).cast(f.type)  # UTC wall time, naive
            else:
                col = col.cast(f.type)
            cols[f.name] = col
    now = datetime.now(UTC).replace(tzinfo=None, microsecond=0)
    cols["detail_level"] = pa.array([detail_level] * n, type=pa.uint8())
    cols["source"] = pa.array([SOURCE_BQ] * n, type=pa.string())
    cols["ingested_at"] = pa.array([now] * n, type=pa.timestamp("us"))
    ordered = pa.table({f.name: cols[f.name] for f in EVENTS_SCHEMA})
    return ordered.cast(pa.schema([pa.field(f.name, f.type) for f in EVENTS_SCHEMA]))


def run_unit(client, cfg: Config, unit: Unit, raw_types: list[str], mode_full: bool) -> Unit:
    from google.cloud import bigquery

    s, e = date.fromisoformat(unit.start), date.fromisoformat(unit.end)
    query = Q.raw_events_sql(s, e, unit.mode)
    params = [bigquery.ArrayQueryParameter("raw_types", "STRING", raw_types)]
    job = client.query(
        query,
        job_config=bigquery.QueryJobConfig(
            query_parameters=params,
            maximum_bytes_billed=cfg.bigquery.per_query_max_bytes_billed,
            use_query_cache=True,
            labels={"project": "gh-breakout"},
        ),
    )
    out_dir = _staging(cfg, unit.month, unit.mode, unit)
    shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    writers: dict[str, pq.ParquetWriter] = {}
    rows: dict[str, int] = {}
    try:
        try:
            from google.cloud import bigquery_storage

            bqs = bigquery_storage.BigQueryReadClient()
        except Exception:  # noqa: BLE001
            bqs = None
        for batch in job.result().to_arrow_iterable(bqstorage_client=bqs):
            if batch.num_rows == 0:
                continue
            t = _to_events_schema(batch, 1 if mode_full else 0)
            # drop rows violating NOT NULL columns (counted under "_bad")
            ok = pc.and_(
                pc.and_(
                    pc.is_valid(t.column("event_id")),
                    pc.is_valid(t.column("repo_id")),
                ),
                pc.and_(
                    pc.is_valid(t.column("actor_id")),
                    pc.is_valid(t.column("created_at")),
                ),
            )
            bad = t.num_rows - pc.sum(ok.cast(pa.int64())).as_py()
            if bad:
                rows["_bad"] = rows.get("_bad", 0) + bad
                t = t.filter(ok)
            types = t.column("event_type").to_pylist()
            for etype in set(types):
                sub = t.filter(pc.equal(t.column("event_type"), etype))
                w = writers.get(etype)
                if w is None:
                    w = pq.ParquetWriter(
                        out_dir / f"event_type={etype}.parquet", _STAGE_SCHEMA, compression="zstd"
                    )
                    writers[etype] = w
                w.write_table(sub)
                rows[etype] = rows.get(etype, 0) + sub.num_rows
    finally:
        for w in writers.values():
            w.close()
        unit.bytes_billed = int(getattr(job, "total_bytes_billed", 0) or 0)
    unit.rows_by_type = rows
    unit.job_id = job.job_id
    return unit


def _connect(spill: Path) -> duckdb.DuckDBPyConnection:
    """Bounded DuckDB connection; use a fresh one per statement (long-lived ones cache memory)."""
    con = duckdb.connect()
    con.execute("SET memory_limit = '1500MB'")
    con.execute(f"SET temp_directory = '{spill.as_posix()}'")
    con.execute("SET threads = 1")
    return con


def _days_index(files: list[str], spill: Path) -> dict[date, list[str]]:
    """Map each calendar day to the staged chunk files that contain rows for it."""
    days_in: dict[date, list[str]] = {}
    for f in files:
        con = _connect(spill)
        rows = con.execute(
            "SELECT DISTINCT CAST(created_at AS DATE) FROM read_parquet(?)", [f]
        ).fetchall()
        con.close()
        for (d,) in rows:
            days_in.setdefault(d, []).append(f)
    return days_in


def _finalize_events(
    cfg: Config, y: int, m: int, etype: str, files: list[str], spill: Path
) -> Path:
    """Build one month file: per-day dedupe on event_id, then one sort-only pass.

    The hash dedupe over a whole month of wide rows plus a second sort exceeds the memory cap;
    per day the dedupe is small, and an external sort over already-unique rows spills cleanly.
    """
    parts_dir = spill / f"parts_{etype}"
    shutil.rmtree(parts_dir, ignore_errors=True)
    parts_dir.mkdir(parents=True, exist_ok=True)
    parts: list[str] = []
    for d, day_files in sorted(_days_index(files, spill).items()):
        part = parts_dir / f"{d:%Y%m%d}.parquet"
        con = _connect(spill)
        con.execute("SET preserve_insertion_order = false")
        con.execute(
            "COPY (SELECT DISTINCT ON (event_id) * FROM read_parquet(?) "
            "WHERE CAST(created_at AS DATE) = ?) "
            f"TO '{part.as_posix()}' (FORMAT parquet, COMPRESSION zstd)",
            [day_files, d],
        )
        con.close()
        parts.append(str(part))
    dest = layout.bq_file(etype, y, m, cfg)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.unlink(missing_ok=True)
    con = _connect(spill)
    con.execute("SET preserve_insertion_order = false")
    con.execute(
        "COPY (SELECT * FROM read_parquet(?) ORDER BY repo_id, created_at, event_id) "
        f"TO '{tmp.as_posix()}' "
        "(FORMAT parquet, COMPRESSION zstd, COMPRESSION_LEVEL 9, ROW_GROUP_SIZE 131072)",
        [parts],
    )
    con.close()
    os.replace(tmp, dest)
    shutil.rmtree(parts_dir, ignore_errors=True)
    return dest


def _finalize_push(cfg: Config, y: int, m: int, files: list[str], spill: Path) -> Path:
    """Build ``push_daily`` for a month one day at a time (bounded memory).

    A month holds ~60M raw push rows, so one global dedupe/aggregate/sort does not fit the cap.
    Per day (~2M rows): dedupe on event_id across every chunk holding that day, aggregate to
    (repo_id, actor_id), then concatenate the day parts in day order (each is already sorted).
    """

    days_in = _days_index(files, spill)
    parts_dir = spill / "push_parts"
    shutil.rmtree(parts_dir, ignore_errors=True)
    parts_dir.mkdir(parents=True, exist_ok=True)
    parts: list[str] = []
    for d in sorted(days_in):
        part = parts_dir / f"{d:%Y%m%d}.parquet"
        con = _connect(spill)
        con.execute(
            "COPY (SELECT repo_id, actor_id, CAST(? AS DATE) AS day, "
            "CAST(count(*) AS INTEGER) AS n_pushes, arg_max(repo_name, event_id) AS repo_name "
            "FROM (SELECT DISTINCT ON (event_id) event_id, repo_id, actor_id, repo_name "
            "FROM read_parquet(?) WHERE CAST(created_at AS DATE) = ?) "
            "GROUP BY repo_id, actor_id ORDER BY repo_id, actor_id) "
            f"TO '{part.as_posix()}' (FORMAT parquet, COMPRESSION zstd)",
            [d, days_in[d], d],
        )
        con.close()
        parts.append(str(part))
    dest = layout.bq_file(PUSH, y, m, cfg)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.unlink(missing_ok=True)
    con = _connect(spill)
    con.execute("SET preserve_insertion_order = true")  # keep day order; streaming, no sort
    con.execute(
        "COPY (SELECT repo_id, actor_id, day, n_pushes, repo_name, 'bq' AS source, "
        "CAST(? AS TIMESTAMP) AS ingested_at FROM read_parquet(?)) "
        f"TO '{tmp.as_posix()}' "
        "(FORMAT parquet, COMPRESSION zstd, COMPRESSION_LEVEL 9, ROW_GROUP_SIZE 131072)",
        [datetime.now(UTC).replace(tzinfo=None, microsecond=0), parts],
    )
    con.close()
    os.replace(tmp, dest)
    shutil.rmtree(parts_dir, ignore_errors=True)
    return dest


def finalize_month(cfg: Config, month: str, mode: str, units: list[Unit]) -> list[Path]:
    """Merge all chunks of a month into ``bq-YYYYMM.parquet`` per event type (+ push_daily)."""
    y, m = map(int, month.split("-"))
    dirs = [_staging(cfg, month, mode, u) for u in units]
    written: list[Path] = []
    # Bounded memory: spill to disk instead of growing (explicit ORDER BY keeps output order).
    # A fresh connection per event type: one long-lived connection accumulates cached metadata
    # and buffers until the later, larger types run out of room under the cap.
    spill = layout.staging_dir(cfg) / "duckdb_spill"
    spill.mkdir(parents=True, exist_ok=True)
    types = set(cfg.events.raw_types) | {PUSH}
    for etype in sorted(types):
        files = [str(d / f"event_type={etype}.parquet") for d in dirs]
        files = [f for f in files if Path(f).exists()]
        if not files:
            continue
        if etype == PUSH:
            written.append(_finalize_push(cfg, y, m, files, spill))
            continue
        written.append(_finalize_events(cfg, y, m, etype, files, spill))
    for d in dirs:
        shutil.rmtree(d, ignore_errors=True)
    shutil.rmtree(spill, ignore_errors=True)
    base = layout.staging_dir(cfg) / "bq" / month.replace("-", "") / mode
    shutil.rmtree(base, ignore_errors=True)
    return written


def estimate_bytes(client, units: list[Unit], raw_types: list[str], workers: int = 3) -> int:
    """Free dry-run estimate of the bytes the given units would scan."""
    from google.cloud import bigquery

    def est(u: Unit) -> int:
        job = client.query(
            Q.raw_events_sql(date.fromisoformat(u.start), date.fromisoformat(u.end), u.mode),
            job_config=bigquery.QueryJobConfig(
                dry_run=True,
                use_query_cache=False,
                query_parameters=[bigquery.ArrayQueryParameter("raw_types", "STRING", raw_types)],
            ),
        )
        return int(job.total_bytes_processed or 0)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return sum(pool.map(est, units))


def run_backfill(
    cfg: Config,
    first: date,
    last: date,
    *,
    mode: str = "spine",
    max_bytes: int | None = None,
    dry: bool = False,
    workers: int = 3,
    manifest_path: Path | None = None,
    client=None,
) -> dict:
    from google.cloud import bigquery

    manifest = Manifest(manifest_path or Path(cfg.bigquery.manifest_path))
    if not manifest_path and not Path(cfg.bigquery.manifest_path).is_absolute():
        from breakout.paths import ROOT

        manifest = Manifest(ROOT / cfg.bigquery.manifest_path)
    manifest.add(make_units(first, last, mode, cfg.bigquery.order))
    manifest.save()

    def finalize_ready() -> None:
        """Finalize months whose chunks are all done (also recovers an interrupted finalize)."""
        for month in sorted({u.month for u in manifest.units.values() if u.mode == mode}):
            mu = manifest.month_units(month, mode)
            if (
                mu
                and all(x.status == "done" for x in mu)
                and _needs_finalize(manifest, month, mode)
                and not dry
            ):
                finalize_month(cfg, month, mode, mu)
                manifest.finalized[month] = mode
                manifest.save()
                log.info("finalized month %s (%s)", month, mode)

    finalize_ready()
    client = client or bigquery.Client(project=cfg.bigquery.require_project_id())
    budget = min(cfg.bigquery.monthly_budget_bytes, max_bytes or cfg.bigquery.monthly_budget_bytes)
    cal = f"{datetime.now(UTC):%Y-%m}"
    raw_types = Q.validate_types(list(cfg.events.raw_types))
    todo = [u for u in manifest.units.values() if u.mode == mode and u.status in ("todo", "failed")]
    todo = [u for u in todo if first.isoformat() <= u.start and u.end <= last.isoformat()]
    todo.sort(key=lambda u: u.start, reverse=cfg.bigquery.order == "newest_first")
    stats: dict[str, int | bool] = {
        "todo": len(todo),
        "done": 0,
        "failed": 0,
        "stopped_for_quota": False,
        "bytes": 0,
    }
    if not todo:
        return stats
    if dry:
        stats["estimated_bytes"] = estimate_bytes(client, todo, raw_types, workers)
        stats["spent_this_month"] = manifest.spent_in(cal)
        stats["budget"] = budget
        return stats

    def one(u: Unit) -> Unit:
        s, e = date.fromisoformat(u.start), date.fromisoformat(u.end)
        dry_job = client.query(
            Q.raw_events_sql(s, e, u.mode),
            job_config=bigquery.QueryJobConfig(
                dry_run=True,
                use_query_cache=False,
                query_parameters=[bigquery.ArrayQueryParameter("raw_types", "STRING", raw_types)],
            ),
        )
        est = int(dry_job.total_bytes_processed or 0)
        with _LOCK:
            if manifest.spent_in(cal) + est + inflight[0] > budget:
                raise QuotaExhausted(f"{u.key}: {est} bytes would exceed the monthly budget")
            inflight[0] += est
        u.status, u.started_at = "running", datetime.now(UTC).isoformat()
        try:
            for attempt in (1, 2):
                try:
                    run_unit(client, cfg, u, raw_types, mode == "full")
                    u.status, u.error = "done", None
                    break
                except Exception as exc:  # noqa: BLE001
                    msg = str(exc)
                    if "quota" in msg.lower() or exc.__class__.__name__ == "Forbidden":
                        u.status = "todo"
                        raise QuotaExhausted(msg) from exc
                    u.error = msg[:500]
                    u.status = "failed"
                    if attempt == 1:
                        log.warning("unit %s failed once: %s", u.key, msg[:200])
        finally:
            with _LOCK:
                inflight[0] -= est
            u.finished_at = datetime.now(UTC).isoformat()
        return u

    inflight = [0]
    stop = threading.Event()

    def guarded(u: Unit) -> Unit | None:
        if stop.is_set():
            return None
        try:
            r = one(u)
        except QuotaExhausted as exc:
            stop.set()
            log.warning("stopping cleanly: %s", exc)
            stats["stopped_for_quota"] = True
            return None
        manifest.save()
        if r.status == "done":
            stats["done"] += 1
            stats["bytes"] += r.bytes_billed
            log.info("done %s: %.2f GB billed, %s", r.key, r.bytes_billed / 1e9, r.rows_by_type)
            month_units = manifest.month_units(r.month, mode)
            if all(x.status == "done" for x in month_units) and _needs_finalize(
                manifest, r.month, mode
            ):
                with _LOCK:
                    finalize_month(cfg, r.month, mode, month_units)
                    manifest.finalized[r.month] = mode
                manifest.save()
                log.info("finalized month %s (%s)", r.month, mode)
        else:
            stats["failed"] += 1
        return r

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(guarded, todo))
    manifest.save()
    return stats
