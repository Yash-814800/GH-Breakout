"""Lake invariants (ADR-010). Cheap structural checks over the local lake.

1. Layout: ``bq-YYYYMM`` files only for months entirely before ``history.cutover_date``;
   ``day-`` files only on/after the cutover (plus ``history.hourly_gap_days``); ``month-`` files
   anywhere. Hive keys in the path agree with the rows (event_type, year, month).
2. Row dates: every row's ``created_at`` lies in the file's month (bq/month) or day (day files);
   push_daily ``day`` likewise.
3. Provenance: ``bq`` files hold only ``source = 'bq'`` and ``detail_level = 0`` before
   ``detail_start_date``; hourly files only ``hourly``/``opendigger`` and ``detail_level = 1``.
4. Uniqueness: ``event_id`` unique within an event type and month; ``push_daily`` unique on
   ``(repo_id, actor_id, day)`` within a month.
5. OpenDigger-sourced rows (``source = 'opendigger'``) are listed so the publisher can exclude
   those files from the public Hugging Face dataset; verification never fails on them.
6. Coverage (Phase 3): no two files cover the same (event_type, day): a month with a ``bq`` or
   ``month`` file has no ``day`` files (except ``history.hourly_gap_days``), and never both ``bq``
   and ``month`` files. Every file's columns/types equal ``schema.py`` and its ``schema_version``
   equals ``SCHEMA_VERSION``.
7. ``--deep``: ``event_id`` unique across all files of an event type and month (scans data).
8. ``--remote``: local catalog vs the catalog on Hugging Face vs the Hub file listing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from breakout.config import Config
from breakout.lake import catalog as cat
from breakout.lake import layout
from breakout.schema import SCHEMA_VERSION


@dataclass
class VerifyReport:
    files_checked: int = 0
    violations: list[str] = field(default_factory=list)
    opendigger_files: list[Path] = field(default_factory=list)
    rows_by_era: dict[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.violations

    def summary_lines(self) -> list[str]:
        out = [f"files checked: {self.files_checked}"]
        out.append(f"rows by era: {self.rows_by_era}")
        out.append(
            f"files containing opendigger rows (never publish): {len(self.opendigger_files)}"
        )
        out.append("OK" if self.ok else f"{len(self.violations)} violation(s):")
        out.extend(f"  - {v}" for v in self.violations[:50])
        return out


def _month_of(path: Path) -> tuple[int, int]:
    year = int(path.parent.parent.name.split("=")[1])
    month = int(path.parent.name.split("=")[1])
    return year, month


def verify_lake(cfg: Config, *, deep: bool = False) -> VerifyReport:
    rep = VerifyReport()
    root = layout.lake_root(cfg)
    cutover = cfg.history.cutover_date
    detail_start = cfg.history.detail_start_date
    gap_days = set(cfg.history.hourly_gap_days)
    con = duckdb.connect()
    era_rows: dict[str, int] = {}

    files = sorted(
        [
            *root.glob("events/event_type=*/year=*/month=*/*.parquet"),
            *root.glob("push_daily/year=*/month=*/*.parquet"),
        ]
    )
    groups: dict[tuple[str, int, int], list[Path]] = {}
    coverage: dict[tuple, list[tuple[str, date | None]]] = {}
    for f in files:
        rep.files_checked += 1
        is_push = "push_daily" in f.parts
        year, month = _month_of(f)
        etype = None if is_push else f.parent.parent.parent.name.split("=")[1]
        name = f.name
        kind = name.split("-")[0]
        first = date(year, month, 1)
        nxt = date(year + (month == 12), month % 12 + 1, 1)
        day: date | None = None
        if kind == "day":
            try:
                day = date.fromisoformat(name.removeprefix("day-").removesuffix(".parquet"))
            except ValueError:
                rep.violations.append(f"{f}: unparsable day file name")
                continue
        # 1. layout vs cutover
        if cutover is not None:
            if kind == "bq" and nxt > cutover:
                rep.violations.append(
                    f"{f}: bq file for a month not entirely before cutover {cutover}"
                )
            if kind == "day" and day is not None and day < cutover and day not in gap_days:
                rep.violations.append(f"{f}: hourly day file before cutover {cutover}")
        # 6. schema / schema_version from the footer (no data scan)
        try:
            info = cat.parse_path(f.relative_to(root).as_posix())
        except ValueError:
            rep.violations.append(f"{f}: unexpected file name")
            continue
        pf = pq.ParquetFile(f)
        want = cat.PUSH_DAILY_SCHEMA if is_push else cat.EVENTS_SCHEMA
        have = pf.schema_arrow
        if have.names != want.names or any(
            have.field(n).type != want.field(n).type for n in want.names
        ):
            rep.violations.append(f"{f}: columns/types differ from schema.py: {have.names}")
        elif cat._schema_version(pf, info["table"]) != SCHEMA_VERSION:
            rep.violations.append(f"{f}: schema_version != {SCHEMA_VERSION}")
        col_day = "day" if is_push else "created_at"
        rows = con.execute(
            f"SELECT count(*), min(CAST({col_day} AS DATE)), max(CAST({col_day} AS DATE)), "
            "       count(*) FILTER (WHERE source = 'opendigger') FROM read_parquet(?)",
            [str(f)],
        ).fetchone()
        n, lo, hi, n_od = rows  # type: ignore[misc]
        if n == 0:
            continue
        if n_od:
            rep.opendigger_files.append(f)
        # 2. row dates
        if kind == "day" and day is not None:
            if lo != day or hi != day:
                rep.violations.append(f"{f}: rows span {lo}..{hi}, expected only {day}")
        elif lo < first or hi >= nxt:
            rep.violations.append(f"{f}: rows span {lo}..{hi}, expected within {first}..{nxt}")
        # era accounting (by file date range; day files are exact)
        probe = day or lo
        era_rows[cfg.era(probe)] = era_rows.get(cfg.era(probe), 0) + n
        # 3. provenance
        cols = {
            r[0] for r in con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(f)]).fetchall()
        }
        srcs = {
            r[0]
            for r in con.execute("SELECT DISTINCT source FROM read_parquet(?)", [str(f)]).fetchall()
        }
        if kind == "bq" and srcs != {"bq"}:
            rep.violations.append(f"{f}: bq file with sources {sorted(srcs)}")
        if kind == "day" and not srcs <= {"hourly", "opendigger"}:
            rep.violations.append(f"{f}: day file with sources {sorted(srcs)}")
        if not is_push and "detail_level" in cols:
            levels = {
                r[0]
                for r in con.execute(
                    "SELECT DISTINCT detail_level FROM read_parquet(?)", [str(f)]
                ).fetchall()
            }
            want_full = kind == "day" or (detail_start is not None and first >= detail_start)
            if want_full and levels != {1} and kind == "day":
                rep.violations.append(
                    f"{f}: hourly file with detail_level {sorted(levels)} (expected 1)"
                )
            if kind == "bq" and (detail_start is None or nxt <= detail_start) and levels != {0}:
                rep.violations.append(
                    f"{f}: spine-era bq file with detail_level {sorted(levels)} (expected 0)"
                )
        # hive key agrees with rows
        if etype is not None:
            bad = con.execute(
                "SELECT count(*) FROM read_parquet(?) WHERE event_type <> ?", [str(f), etype]
            ).fetchone()
            if bad and bad[0]:
                rep.violations.append(f"{f}: {bad[0]} rows with event_type != {etype}")
        # 4. uniqueness
        coverage.setdefault((info["table"], info["event_type"], year, month), []).append(
            (kind, day)
        )
        if is_push:
            dup = con.execute(
                "SELECT count(*) FROM (SELECT 1 FROM read_parquet(?) "
                "GROUP BY repo_id, actor_id, day HAVING count(*) > 1)",
                [str(f)],
            ).fetchone()
            if dup and dup[0]:
                rep.violations.append(f"{f}: {dup[0]} duplicated (repo_id, actor_id, day) groups")
        else:
            groups.setdefault((str(etype), year, month), []).append(f)
    for (_table, etype, year, month), members in coverage.items():
        kinds = {k for k, _ in members}
        label = f"{etype or 'push_daily'} {year}-{month:02d}"
        if {"bq", "month"} <= kinds:
            rep.violations.append(f"{label}: both bq and month files")
        if kinds & {"bq", "month"}:
            stray = [d for k, d in members if k == "day" and d not in gap_days]
            if stray:
                rep.violations.append(
                    f"{label}: day files {[str(d) for d in stray[:3]]} overlap a bq/month file"
                )
    # 7. event_id unique within an event type and month, across all files of that month
    for (etype, year, month), fs in groups.items() if deep else ():
        dup = con.execute(
            "SELECT count(*) - count(DISTINCT event_id) FROM read_parquet(?)",
            [[str(x) for x in fs]],
        ).fetchone()
        if dup and dup[0]:
            rep.violations.append(
                f"{etype} {year}-{month:02d}: {dup[0]} duplicate event_ids across {len(fs)} file(s)"
            )
    rep.rows_by_era = era_rows
    return rep


def verify_remote(cfg: Config, api, local: pa.Table) -> list[str]:
    """Compare the local catalog with the Hub: returns violation strings (empty = consistent).

    Files only present locally are not violations (not pushed yet) and are reported separately by
    the CLI; anything the remote catalog and the Hub listing disagree on is.
    """
    from breakout.lake import hf, sync

    out: list[str] = []
    remote, _ = sync.fetch_remote_catalog(api, cfg)
    listing = {f.path: f for f in hf.remote_list(api, cfg, "events")}
    r_rows = {r["path"]: r for r in remote.to_pylist()}
    l_rows = {r["path"]: r for r in local.to_pylist()}
    for path, r in r_rows.items():
        f = listing.get(path)
        if f is None:
            out.append(f"{path}: in the remote catalog but not in the repo")
        elif f.sha256 != r["sha256"] or f.size != r["bytes"]:
            out.append(f"{path}: remote catalog differs from the Hub file (sha/size)")
        mine = l_rows.get(path)
        if mine is not None and mine["sha256"] != r["sha256"]:
            out.append(f"{path}: local file differs from the remote (sha256)")
    skip = {hf.CATALOG_PATH, "README.md", ".gitattributes"}
    for path in listing:
        if path not in r_rows and path not in skip and not path.startswith("manifests/"):
            out.append(f"{path}: in the repo but missing from the remote catalog")
    return out
