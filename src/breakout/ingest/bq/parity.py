"""Train/serve parity: one day through the hourly parser vs the same day from BigQuery.

Both outputs go to scratch lake roots (never the real lake). Every shared event is compared
column by column, not just a sample, which is stricter than the phase's 1,000-row check.
"""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import duckdb

from breakout.config import Config
from breakout.ingest.bq.run import run_backfill
from breakout.lake import layout
from breakout.logging import get_logger
from breakout.paths import ROOT
from breakout.schema import EVENTS_COLUMNS

log = get_logger(__name__)

SKIP_COLS = {"event_id", "source", "ingested_at"}
TS_COLS = {"created_at", "target_created_at"}
COUNT_TOLERANCE = 0.001


def _scratch_cfg(cfg: Config, root: Path) -> Config:
    lake = cfg.lake.model_copy(update={"local_root": str(root / "lake")})
    return cfg.model_copy(update={"lake": lake})


def _one(con: duckdb.DuckDBPyConnection, sql: str) -> tuple:
    row = con.execute(sql).fetchone()
    assert row is not None
    return row


def _src(file: Path, day: date) -> str:
    return (
        f"(SELECT * FROM read_parquet('{file.as_posix()}') "
        f"WHERE CAST(created_at AS DATE) = DATE '{day.isoformat()}')"
    )


def compare_files(
    hourly: dict[str, Path], bq: dict[str, Path], day: date, *, compare_detail: bool
) -> dict:
    """Compare per-event-type files; returns a JSON-able result dict."""
    con = duckdb.connect()
    cols = [c for c in EVENTS_COLUMNS if c not in SKIP_COLS]
    if not compare_detail:
        detail = {
            "action", "number", "is_pull_request", "target_user_id", "target_created_at",
            "pr_merged", "review_state", "ref_type", "forkee_repo_id", "release_prerelease",
            "detail_level",
        }  # fmt: skip
        cols = [c for c in cols if c not in detail]
    out: dict = {"types": {}, "ok": True}
    for etype in sorted(set(hourly) | set(bq)):
        h, b = hourly.get(etype), bq.get(etype)
        res: dict = {"hourly_rows": 0, "bq_rows": 0}
        if h:
            res["hourly_rows"] = _one(con, f"select count(*) from {_src(h, day)}")[0]
        if b:
            res["bq_rows"] = _one(con, f"select count(*) from {_src(b, day)}")[0]
        if h and b:
            hs, bs = _src(h, day), _src(b, day)
            res["only_hourly"] = _one(
                con, f"select count(*) from {hs} where event_id not in (select event_id from {bs})"
            )[0]
            res["only_bq"] = _one(
                con, f"select count(*) from {bs} where event_id not in (select event_id from {hs})"
            )[0]
            exprs = []
            for c in cols:
                ca, cb = f"h.{c}", f"b.{c}"
                if c in TS_COLS:
                    ca, cb = f"date_trunc('second', {ca})", f"date_trunc('second', {cb})"
                exprs.append(f"count(*) filter (where {ca} is distinct from {cb}) as {c}")
            row = _one(
                con,
                f"select count(*) as shared, {', '.join(exprs)} "
                f"from {hs} h join {bs} b using (event_id)",
            )
            res["shared"] = row[0]
            res["column_mismatches"] = {c: v for c, v in zip(cols, row[1:], strict=True) if v}
        n = max(res["hourly_rows"], res["bq_rows"], 1)
        res["count_diff_pct"] = round(100 * abs(res["hourly_rows"] - res["bq_rows"]) / n, 4)
        res["pass"] = (
            res["count_diff_pct"] <= COUNT_TOLERANCE * 100
            and not res.get("column_mismatches")
            and res.get("only_hourly", 0) + res.get("only_bq", 0) <= COUNT_TOLERANCE * n
        )
        out["ok"] &= res["pass"]
        out["types"][etype] = res
    return out


def compare_push(h: Path | None, b: Path | None, day: date) -> dict:
    if not (h and b):
        return {"pass": False, "note": "missing file"}
    con = duckdb.connect()
    hs = f"(select * from read_parquet('{h.as_posix()}') where day = DATE '{day}')"
    bs = f"(select * from read_parquet('{b.as_posix()}') where day = DATE '{day}')"
    r = _one(
        con,
        f"select (select count(*) from {hs}), (select count(*) from {bs}), "
        f"(select sum(n_pushes) from {hs}), (select sum(n_pushes) from {bs}), "
        f"(select count(*) from {hs} h full join {bs} b using (repo_id, actor_id, day) "
        f"where h.n_pushes is distinct from b.n_pushes)",
    )
    return {
        "hourly_rows": r[0],
        "bq_rows": r[1],
        "hourly_pushes": r[2],
        "bq_pushes": r[3],
        "mismatched_groups": r[4],
        "pass": r[4] == 0,
    }


def run_parity(cfg: Config, day: date, *, mode: str = "full", workdir: Path | None = None) -> dict:
    from breakout.ingest.day import ingest_day

    work = workdir or (ROOT / "data" / "parity" / day.isoformat())
    shutil.rmtree(work, ignore_errors=True)
    hcfg, bcfg = _scratch_cfg(cfg, work / "hourly"), _scratch_cfg(cfg, work / "bq")
    log.info("parity %s: hourly ingest", day)
    summary = ingest_day(day, cfg=hcfg, keep_raw=False)
    log.info("parity %s: bigquery %s extraction", day, mode)
    stats = run_backfill(bcfg, day, day, mode=mode, manifest_path=work / "bq_manifest.json")
    types = list(cfg.events.raw_types)
    hourly = {t: layout.day_file(t, day, hcfg) for t in types}
    bq = {t: layout.bq_file(t, day.year, day.month, bcfg) for t in types}
    res = compare_files(
        {t: p for t, p in hourly.items() if p.exists()},
        {t: p for t, p in bq.items() if p.exists()},
        day,
        compare_detail=mode == "full",
    )
    res["push"] = compare_push(
        layout.day_file("PushEvent", day, hcfg)
        if layout.day_file("PushEvent", day, hcfg).exists()
        else None,
        layout.bq_file("PushEvent", day.year, day.month, bcfg)
        if layout.bq_file("PushEvent", day.year, day.month, bcfg).exists()
        else None,
        day,
    )
    res["ok"] = bool(res["ok"] and res["push"]["pass"])
    res.update(
        day=day.isoformat(),
        mode=mode,
        hours_ok=summary.hours_ok + summary.hours_skipped,
        missing_hours=summary.missing_hours,
        bytes_billed=stats.get("bytes", 0),
    )
    return res


def render_report(results: list[dict]) -> str:
    lines = [
        "# BigQuery vs hourly-parser parity",
        "",
        "Generated by `breakout backfill parity`. Each day is parsed twice: from the hourly "
        "files with the production parser and from `githubarchive.day.*` with the backfill SQL. "
        "Every shared `event_id` is compared on every column (timestamps to the second).",
        "",
    ]
    for r in results:
        lines += [
            f"## {r['day']} ({r['mode']} mode): {'PASS' if r['ok'] else 'FAIL'}",
            "",
            f"- hours parsed: {r['hours_ok']}/24, missing {r['missing_hours']}; "
            f"BigQuery billed {r['bytes_billed'] / 1e9:.2f} GB",
            "",
            "| event type | hourly rows | BQ rows | diff % | only hourly | only BQ | shared | "
            "mismatched columns | result |",
            "|---|---:|---:|---:|---:|---:|---:|---|---|",
        ]
        for t, v in r["types"].items():
            lines.append(
                f"| {t} | {v['hourly_rows']:,} | {v['bq_rows']:,} | {v['count_diff_pct']} | "
                f"{v.get('only_hourly', '')} | {v.get('only_bq', '')} | {v.get('shared', '')} | "
                f"{v.get('column_mismatches') or 'none'} | {'ok' if v['pass'] else 'FAIL'} |"
            )
        p = r["push"]
        lines += [
            "",
            f"push_daily: {p}",
            "",
        ]
    return "\n".join(lines)
