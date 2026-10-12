"""Command line interface (``breakout``). Groups are stubs until their phase lands."""

from __future__ import annotations

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


lake_app = typer.Typer(help="Lake maintenance (Phase 3).", no_args_is_help=True)
app.add_typer(lake_app, name="lake")


@lake_app.command("verify")
def lake_verify_cmd(ctx: typer.Context) -> None:
    """Check lake invariants (ADR-010); exit 1 on violations."""
    from breakout.lake.verify import verify_lake

    cfg = get_config(ctx.obj["config"])
    report = verify_lake(cfg)
    for line in report.summary_lines():
        typer.echo(line)
    if not report.ok:
        raise typer.Exit(1)


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
