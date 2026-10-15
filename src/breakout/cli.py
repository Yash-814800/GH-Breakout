"""Command line interface (``breakout``). Groups are stubs until their phase lands."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated

import typer

from breakout import __version__
from breakout import paths as P
from breakout.config import get_config

app = typer.Typer(help="gh-breakout: predict GitHub repo breakouts.", no_args_is_help=True)

ENV_VARS = (
    "HF_TOKEN",
    "HF_USER",
    "GH_ENRICH_TOKEN",
    "GCP_PROJECT_ID",
    "BLUESKY_HANDLE",
    "BLUESKY_APP_PASSWORD",
)

_STUBS = {
    "enrich": 4,
    "build": 5,
    "ml": 6,
    "daily": 9,
    "publish": 10,
    "ops": 9,
}


def _make_stub(name: str, phase: int) -> typer.Typer:
    group = typer.Typer(help=f"{name} commands (Phase {phase}).", invoke_without_command=True)

    @group.callback()
    def _stub() -> None:
        typer.echo(f"{name}: not implemented yet (Phase {phase})")

    return group


for _name, _phase in _STUBS.items():
    app.add_typer(_make_stub(_name, _phase), name=_name)

backfill_app = typer.Typer(help="BigQuery historical backfill (Phase 2).", no_args_is_help=True)
app.add_typer(backfill_app, name="backfill")


@backfill_app.command("survey")
def backfill_survey_cmd(
    ctx: typer.Context,
    last: Annotated[str, typer.Option(help="last day to survey, YYYY-MM-DD")] = "2026-09-05",
) -> None:
    """Dry-run every month (free) and save data/manifests/bq_cost_survey.json."""
    from datetime import date

    from breakout.ingest.bq.survey import run_survey

    cfg = get_config(ctx.obj["config"])
    out = P.MANIFEST_DIR / "bq_cost_survey.json"
    survey = run_survey(
        cfg.history.start_date,
        date.fromisoformat(last),
        cfg.events.raw_types,
        out,
        project=cfg.bigquery.require_project_id(),
    )
    typer.echo(f"surveyed {len(survey['months'])} months -> {out}")
    typer.echo(f"missing day tables: {len(survey['missing_day_tables'])}")


@backfill_app.command("plan")
def backfill_plan_cmd(
    ctx: typer.Context,
    spent_gb: Annotated[float, typer.Option(help="GB already used this calendar month")] = 0.0,
    dry: Annotated[Path, typer.Option(help="spine dry-run JSON")] = P.MANIFEST_DIR
    / "bq_dry_run_spine_2015_2023-05.json",
    out: Annotated[Path, typer.Option(help="markdown output")] = P.ROOT
    / "docs"
    / "bigquery_cost_plan.md",
) -> None:
    """Write docs/bigquery_cost_plan.md from the dry-run JSON (no BigQuery call)."""
    import json
    from datetime import UTC, datetime

    from breakout.ingest.bq import report

    cfg = get_config(ctx.obj["config"])
    if cfg.history.cutover_date is None:
        raise typer.BadParameter("history.cutover_date is not set")
    survey = json.loads((P.MANIFEST_DIR / "bq_cost_survey.json").read_text())
    est_path = P.MANIFEST_DIR / "hourly_download_estimate.json"
    est = json.loads(est_path.read_text()) if est_path.exists() else None
    today = datetime.now(UTC).date()
    md = report.render(
        survey,
        json.loads(dry.read_text()),
        cutover=cfg.history.cutover_date,
        trusted_end=cfg.history.trusted_end,
        budget=cfg.bigquery.monthly_budget_bytes,
        per_query_cap=cfg.bigquery.per_query_max_bytes_billed,
        spent_first=int(spent_gb * 1e9),
        first_calendar_month=f"{today:%Y-%m}",
        hourly_estimate=est,
        generated=today,
    )
    out.write_text(md, encoding="utf-8")
    typer.echo(f"wrote {out}")


@backfill_app.command("run")
def backfill_run_cmd(
    ctx: typer.Context,
    since: Annotated[
        str | None, typer.Option(help="first month YYYY-MM (default start_date)")
    ] = None,
    until: Annotated[
        str | None, typer.Option(help="last month YYYY-MM (default month before cutover)")
    ] = None,
    max_gb: Annotated[float | None, typer.Option(help="cap on GB scanned this run")] = None,
    mode: Annotated[str, typer.Option(help="spine | full")] = "spine",
    dry: Annotated[bool, typer.Option("--dry")] = False,
    workers: Annotated[int, typer.Option(min=1, max=6)] = 3,
) -> None:
    """Run (or resume) the BigQuery extraction; stops cleanly when the budget is reached."""
    import calendar
    from datetime import date, timedelta

    from breakout.ingest.bq.run import run_backfill

    cfg = get_config(ctx.obj["config"])
    if cfg.history.cutover_date is None:
        raise typer.BadParameter("history.cutover_date is not set")
    first = date.fromisoformat(since + "-01") if since else cfg.history.start_date
    if until:
        y, m = map(int, until.split("-"))
        last = date(y, m, calendar.monthrange(y, m)[1])
    else:
        last = cfg.history.cutover_date - timedelta(days=1)
    stats = run_backfill(
        cfg,
        first,
        last,
        mode=mode,
        max_bytes=int(max_gb * 1e9) if max_gb else None,
        dry=dry,
        workers=workers,
    )
    typer.echo(json.dumps(stats))


@backfill_app.command("parity")
def backfill_parity_cmd(
    ctx: typer.Context,
    day: Annotated[list[str], typer.Option(help="YYYY-MM-DD; repeat for several days")],
    mode: Annotated[str, typer.Option(help="spine | full")] = "full",
    report: Annotated[Path, typer.Option(help="markdown report path")] = Path(
        "docs/parity_report.md"
    ),
) -> None:
    """Compare hourly-parser output with the BigQuery extraction for given days."""
    from datetime import date

    from breakout.ingest.bq.parity import render_report, run_parity

    cfg = get_config(ctx.obj["config"])
    results = [run_parity(cfg, date.fromisoformat(d), mode=mode) for d in day]
    report.write_text(render_report(results), encoding="utf-8")
    typer.echo(
        f"wrote {report}: "
        + ", ".join(f"{r['day']}={'PASS' if r['ok'] else 'FAIL'}" for r in results)
    )
    if not all(r["ok"] for r in results):
        raise typer.Exit(1)


@backfill_app.command("hourly")
def backfill_hourly_cmd(
    ctx: typer.Context,
    start: Annotated[str | None, typer.Option(help="first day (default cutover_date)")] = None,
    end: Annotated[str | None, typer.Option(help="last day (default last complete day)")] = None,
    workers: Annotated[int, typer.Option(min=1, max=4, help="concurrent downloads, <= 4")] = 2,
    dry: Annotated[bool, typer.Option("--dry", help="print the plan and exit")] = False,
    force: Annotated[bool, typer.Option("--force")] = False,
) -> None:
    """Resumable backfill from hourly files: trusted era first, then the degraded era."""
    from datetime import date

    from breakout.ingest.backfill import plan_days, run_hourly_backfill

    cfg = get_config(ctx.obj["config"])
    days = plan_days(
        cfg,
        start=date.fromisoformat(start) if start else None,
        end=date.fromisoformat(end) if end else None,
    )
    by_era: dict[str, list] = {}
    for pd in days:
        by_era.setdefault(pd.era, []).append(pd.day)
    for era, ds in by_era.items():
        typer.echo(f"{era}: {len(ds)} days, {min(ds)} .. {max(ds)}")
    if dry:
        return

    def report(pd, s) -> None:
        typer.echo(
            f"{pd.day} [{pd.era}] ok={s.hours_ok}/24 processed={s.hours_processed} "
            f"missing={s.missing_hours} pending={s.pending_hours} error={s.error_hours}"
        )

    run_hourly_backfill(cfg, days, workers=workers, force=force, on_day=report)


lake_app = typer.Typer(
    help="Lake on Hugging Face: init, push, pull, compact, verify (Phase 3).", no_args_is_help=True
)
app.add_typer(lake_app, name="lake")


def _parse_month(value: str) -> tuple[int, int]:
    try:
        y, m = value.split("-")
        year, month = int(y), int(m)
        if not 1 <= month <= 12:
            raise ValueError
    except ValueError as exc:
        raise typer.BadParameter(f"expected YYYY-MM, got {value!r}") from exc
    return year, month


def _require_lake(cfg) -> Path:
    """The lake root must be reachable (the SSD mounted); never create it implicitly."""
    from breakout.lake import layout

    root = layout.lake_root(cfg)
    if not root.exists():
        typer.echo(f"lake root {root} does not exist; is the Lexar SSD mounted?", err=True)
        raise typer.Exit(2)
    return root


@lake_app.command("init")
def lake_init_cmd(ctx: typer.Context) -> None:
    """Create the four public repos (idempotent) and write/update their dataset cards."""
    from breakout.lake import cards, hf, sync

    cfg = get_config(ctx.obj["config"])
    api = hf.get_api()
    repos = hf.ensure_repos(cfg, api)
    remote, _ = sync.fetch_remote_catalog(api, cfg)
    tmp = P.ensure_dir(P.TMP_DIR / "cards")
    for key, text in cards.render_all(cfg, remote).items():
        path = tmp / f"{key}.README.md"
        path.write_text(text, encoding="utf-8")
        commit = hf.put_small_files(
            api, cfg, key, [hf.UploadItem(path, "README.md")], "update dataset card"
        )
        typer.echo(f"{key}: {repos[key]} card {'updated' if commit else 'unchanged'}")


@lake_app.command("push")
def lake_push_cmd(
    ctx: typer.Context,
    table: Annotated[str, typer.Option(help="events | push_daily | all")] = "all",
    since: Annotated[str | None, typer.Option(help="first month YYYY-MM")] = None,
    until: Annotated[str | None, typer.Option(help="last month YYYY-MM")] = None,
    include_days: Annotated[
        bool, typer.Option("--include-days", help="also push day-*.parquet files")
    ] = False,
    dry: Annotated[
        bool, typer.Option("--dry", help="list what would be uploaded and exit")
    ] = False,
) -> None:
    """Upload new/changed local files (month order), then manifests and catalog (resumable)."""
    from breakout.lake import cards, hf, layout, sync
    from breakout.lake import catalog as cat

    cfg = get_config(ctx.obj["config"])
    root = _require_lake(cfg)
    if table not in ("events", "push_daily", "all"):
        raise typer.BadParameter("--table must be events, push_daily or all")
    tables = (cat.EVENTS_TABLE, cat.PUSH_TABLE) if table == "all" else (table,)
    lo = _parse_month(since) if since else None
    hi = _parse_month(until) if until else None
    files = []
    for f in cat.lake_files(root, tables):
        info = cat.parse_path(f.relative_to(root).as_posix())
        ym = (info["year"], info["month"])
        if (lo and ym < lo) or (hi and ym > hi):
            continue
        if info["kind"] == "day" and not include_days:
            continue
        files.append(f)
    total = sum(f.stat().st_size for f in files)
    typer.echo(f"{len(files)} local file(s), {total / 1e9:.2f} GB candidate")
    if dry:
        return
    api = hf.get_api()
    hf.ensure_repos(cfg, api)
    cache = hf.ShaCache(layout.data_root(cfg) / "catalog_cache.json")
    # refuse files that contain OpenDigger rows (never published)
    probe = cat.build_catalog(root, files=files, cache=cache)
    bad = [r["path"] for r in probe.to_pylist() if r["source_max"] == "opendigger"]
    if bad:
        typer.echo(f"refusing to push {len(bad)} file(s) with opendigger rows: {bad[:3]}", err=True)
        raise typer.Exit(1)
    cache.save()
    extra = sync.small_items(
        layout.lake_root(cfg),
        [f"manifests/{n}" for n in ("bq_backfill.json",)],
    )

    def progress(i: int, n: int, size: int) -> None:
        typer.echo(f"commit {i}/{n} done ({size / 1e9:.2f} GB)")

    commits = sync.push_files(
        api,
        cfg,
        root,
        files,
        f"lake push ({table}{' since ' + since if since else ''})",
        extra=extra,
        cache=cache,
        progress=progress,
    )
    cache.save()
    # refresh the dataset card from the new catalog
    remote, _ = sync.fetch_remote_catalog(api, cfg)
    card = P.ensure_dir(P.TMP_DIR / "cards") / "events.README.md"
    card.write_text(cards.render_events(cfg, remote), encoding="utf-8")
    hf.put_small_files(
        api, cfg, "events", [hf.UploadItem(card, "README.md")], "update dataset card"
    )
    rows = remote.to_pylist()
    typer.echo(
        f"{len(commits)} commit(s); remote now {len(rows)} files, "
        f"{sum(r['bytes'] for r in rows) / 1e9:.2f} GB, {sum(r['rows'] for r in rows):,} rows"
    )


@lake_app.command("pull")
def lake_pull_cmd(
    ctx: typer.Context,
    types: Annotated[str | None, typer.Option(help="comma list, e.g. WatchEvent,ForkEvent")] = None,
    since: Annotated[str | None, typer.Option(help="first day YYYY-MM-DD")] = None,
    until: Annotated[str | None, typer.Option(help="last day YYYY-MM-DD")] = None,
    push_daily: Annotated[bool, typer.Option("--push-daily")] = False,
    to: Annotated[
        Path | None, typer.Option(help="destination lake root (default data/lake)")
    ] = None,
    manifests: Annotated[bool, typer.Option("--manifests", help="also fetch manifests/")] = False,
    workers: Annotated[int, typer.Option(min=1, max=8)] = 8,
) -> None:
    """Download only the files covering the range (uses the remote catalog)."""
    from datetime import date

    from breakout.lake import hf, sync

    cfg = get_config(ctx.obj["config"])
    if to is None:
        _require_lake(cfg)
    api = hf.get_api()
    got = sync.pull(
        api,
        cfg,
        types=[t for t in types.split(",") if t] if types else None,
        start=date.fromisoformat(since) if since else None,
        end=date.fromisoformat(until) if until else None,
        push_daily=push_daily,
        to=to,
        workers=workers,
        manifests=manifests,
    )
    typer.echo(f"{len(got)} file(s), {sum(p.stat().st_size for p in got) / 1e9:.2f} GB")
    for p in got[:50]:
        typer.echo(f"  {p}")


@lake_app.command("compact")
def lake_compact_cmd(
    ctx: typer.Context,
    month: Annotated[str, typer.Option(help="YYYY-MM")],
    push: Annotated[bool, typer.Option("--push/--no-push")] = True,
    force: Annotated[
        bool, typer.Option("--force", help="compact even if hours are pending")
    ] = False,
    memory_limit: Annotated[str, typer.Option(help="DuckDB memory_limit per statement")] = "1500MB",
) -> None:
    """Merge a finished month's day files into month files (one atomic Hub commit with --push)."""
    from breakout.lake import compact

    cfg = get_config(ctx.obj["config"])
    _require_lake(cfg)
    y, m = _parse_month(month)
    res = compact.compact_month(cfg, y, m, push=push, force=force, memory_limit=memory_limit)
    typer.echo(
        f"{y:04d}-{m:02d}: {res.status} {res.reason} written={len(res.written)} "
        f"day_files={len(res.day_files)} removed_local={len(res.removed_local)} "
        f"commits={len(res.commits)}"
    )
    if res.status == "incomplete":
        raise typer.Exit(3)


@lake_app.command("backfill-month")
def lake_backfill_month_cmd(
    ctx: typer.Context,
    month: Annotated[str, typer.Argument(help="YYYY-MM (>= cutover month)")],
    workers: Annotated[int, typer.Option(min=1, max=4, help="days in flight (1 hour each)")] = 2,
    memory_limit: Annotated[str, typer.Option()] = "3GB",
) -> None:
    """Actions job body: ingest a month of hourly files, compact, push (skips finished months)."""
    from breakout.lake import backfill_month

    cfg = get_config(ctx.obj["config"])
    y, m = _parse_month(month)
    run = backfill_month.run_month(cfg, y, m, workers=workers, memory_limit=memory_limit)
    typer.echo(json.dumps(run.__dict__))


@lake_app.command("backfill-gap-days")
def lake_backfill_gap_days_cmd(
    ctx: typer.Context,
    workers: Annotated[int, typer.Option(min=1, max=4)] = 2,
) -> None:
    """Actions job body: ingest history.hourly_gap_days and push them as day files."""
    from breakout.lake import backfill_month

    cfg = get_config(ctx.obj["config"])
    typer.echo(json.dumps(backfill_month.run_gap_days(cfg, workers=workers).__dict__))


@lake_app.command("verify")
def lake_verify_cmd(
    ctx: typer.Context,
    deep: Annotated[bool, typer.Option("--deep", help="scan for duplicate event_ids")] = False,
    remote: Annotated[bool, typer.Option("--remote", help="compare with the Hub")] = False,
) -> None:
    """Check lake invariants (ADR-010, Phase 3); exit 1 on violations."""
    from breakout.lake import catalog as cat
    from breakout.lake import hf, layout
    from breakout.lake.verify import verify_lake, verify_remote

    cfg = get_config(ctx.obj["config"])
    root = _require_lake(cfg)
    report = verify_lake(cfg, deep=deep)
    for line in report.summary_lines():
        typer.echo(line)
    ok = report.ok
    if remote:
        cache = hf.ShaCache(layout.data_root(cfg) / "catalog_cache.json")
        local = cat.build_catalog(root, cache=cache)
        cache.save()
        problems = verify_remote(cfg, hf.get_api(), local)
        typer.echo(f"remote: {len(problems)} problem(s)")
        for line in problems[:50]:
            typer.echo(f"  - {line}")
        ok = ok and not problems
    if not ok:
        raise typer.Exit(1)


@lake_app.command("catalog")
def lake_catalog_cmd(
    ctx: typer.Context,
    write: Annotated[Path | None, typer.Option(help="write the local catalog here")] = None,
) -> None:
    """Build the local catalog from Parquet footers and print totals."""
    from breakout.lake import catalog as cat
    from breakout.lake import hf, layout

    cfg = get_config(ctx.obj["config"])
    root = _require_lake(cfg)
    cache = hf.ShaCache(layout.data_root(cfg) / "catalog_cache.json")
    table = cat.build_catalog(root, cache=cache)
    cache.save()
    rows = table.to_pylist()
    typer.echo(
        f"{len(rows)} files, {sum(r['bytes'] for r in rows) / 1e9:.2f} GB, "
        f"{sum(r['rows'] for r in rows):,} rows"
    )
    if write:
        cat.write_catalog(table, write)
        typer.echo(f"wrote {write}")


ingest_app = typer.Typer(help="Hourly GH Archive ingest (Phase 1).", no_args_is_help=True)
app.add_typer(ingest_app, name="ingest")


def _echo_summary(summary) -> None:
    typer.echo(
        f"{summary.day}: processed={summary.hours_processed} skipped={summary.hours_skipped} "
        f"ok={summary.hours_ok}/24 missing={summary.missing_hours} "
        f"pending={summary.pending_hours} error={summary.error_hours}"
    )
    for etype, n in sorted(summary.rows_per_type.items()):
        typer.echo(f"  {etype}: {n:,}")


@ingest_app.command("hour")
def ingest_hour_cmd(
    ctx: typer.Context,
    hour: Annotated[str, typer.Argument(help="UTC hour, e.g. 2024-06-01T12")],
    force: Annotated[bool, typer.Option("--force")] = False,
    keep_raw: Annotated[bool, typer.Option("--keep-raw")] = False,
) -> None:
    """Ingest a single hour (stage it and rebuild that day's files)."""
    from datetime import datetime

    from breakout.ingest.day import ingest_day

    ts = datetime.fromisoformat(hour)
    if ts.minute or ts.second or ts.microsecond:
        raise typer.BadParameter("hour must be a whole hour, e.g. 2024-06-01T12")
    cfg = get_config(ctx.obj["config"])
    _echo_summary(
        ingest_day(ts.date(), force=force, keep_raw=keep_raw, cfg=cfg, only_hours={ts.hour})
    )


@ingest_app.command("day")
def ingest_day_cmd(
    ctx: typer.Context,
    day: Annotated[str, typer.Argument(help="UTC day, YYYY-MM-DD")],
    force: Annotated[bool, typer.Option("--force")] = False,
    keep_raw: Annotated[bool, typer.Option("--keep-raw")] = False,
) -> None:
    """Ingest all 24 hours of a day and build the day files."""
    from datetime import date

    from breakout.ingest.day import ingest_day

    cfg = get_config(ctx.obj["config"])
    _echo_summary(ingest_day(date.fromisoformat(day), force=force, keep_raw=keep_raw, cfg=cfg))


@ingest_app.command("range")
def ingest_range_cmd(
    ctx: typer.Context,
    start: Annotated[str, typer.Argument(help="first UTC day, YYYY-MM-DD")],
    end: Annotated[str, typer.Argument(help="last UTC day (inclusive), YYYY-MM-DD")],
    workers: Annotated[int, typer.Option("--workers", min=1)] = 2,
    force: Annotated[bool, typer.Option("--force")] = False,
    keep_raw: Annotated[bool, typer.Option("--keep-raw")] = False,
) -> None:
    """Ingest an inclusive range of days, ``--workers`` days at a time."""
    from concurrent.futures import ThreadPoolExecutor
    from datetime import date, timedelta

    from breakout.ingest.day import ingest_day

    cfg = get_config(ctx.obj["config"])
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if last < first:
        raise typer.BadParameter("end must be >= start")
    days = [first + timedelta(days=i) for i in range((last - first).days + 1)]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(ingest_day, d, force=force, keep_raw=keep_raw, cfg=cfg, hour_workers=1)
            for d in days
        ]
        for fut in futures:
            _echo_summary(fut.result())


@ingest_app.command("audit")
def ingest_audit_cmd(
    ctx: typer.Context,
    keep_raw: Annotated[bool, typer.Option("--keep-raw")] = False,
) -> None:
    """Download sample hours, write docs/schema_audit.md and test fixtures."""
    from breakout.ingest.audit import run_audit
    from breakout.lake import layout

    cfg = get_config(ctx.obj["config"])
    types = [*cfg.events.raw_types, *cfg.events.aggregated_types]
    out = run_audit(
        types,
        raw_dir=layout.raw_dir(cfg) / "audit",
        cache_dir=layout.data_root(cfg) / "audit",
        fixture_dir=P.ROOT / "tests" / "fixtures",
        docs_path=P.ROOT / "docs" / "schema_audit.md",
        keep_raw=keep_raw,
    )
    typer.echo(f"wrote {out}")


@app.callback()
def main(
    ctx: typer.Context,
    config: Annotated[
        Path | None,
        typer.Option("--config", envvar="BREAKOUT_CONFIG", help="Path to a project.yaml."),
    ] = None,
) -> None:
    ctx.obj = {"config": config}


@app.command()
def info(ctx: typer.Context) -> None:
    """Print a config summary and resolved paths. Secrets show only 'set' / 'not set'."""
    cfg = get_config(ctx.obj["config"])
    typer.echo(f"breakout {__version__}")
    typer.echo(f"project: {cfg.project.name} (timezone {cfg.project.timezone})")
    typer.echo(f"history: {cfg.history.start_date} -> cutover {cfg.history.cutover_date}")
    typer.echo(f"labels: horizon {cfg.labels.horizon_days}d, primary {cfg.labels.primary}")
    typer.echo("environment:")
    for var in ENV_VARS:
        typer.echo(f"  {var}: {'set' if os.environ.get(var) else 'not set'}")
    typer.echo(f"  LOG_LEVEL: {os.environ.get('LOG_LEVEL', 'INFO (default)')}")
    typer.echo("paths:")
    for label, value in (
        ("root", P.ROOT),
        ("config", ctx.obj["config"] or P.CONFIG_PATH),
        ("data", P.DATA_DIR),
        ("lake", P.LAKE_DIR),
        ("manifests", P.MANIFEST_DIR),
        ("warehouse", P.WAREHOUSE),
    ):
        typer.echo(f"  {label}: {value}")


if __name__ == "__main__":
    app()
