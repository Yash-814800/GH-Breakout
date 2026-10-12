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
    "lake": 3,
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
    cutover: Annotated[str, typer.Option(help="proposed cutover date")] = "2026-09-06",
    spent_gb: Annotated[float, typer.Option(help="GB already used this calendar month")] = 0.0,
    out: Annotated[Path, typer.Option(help="markdown output")] = P.ROOT
    / "docs"
    / "bigquery_cost_plan.md",
) -> None:
    """Pack the surveyed work into free quota months and write docs/bigquery_cost_plan.md."""
    import json
    from datetime import UTC, date, datetime

    from breakout.ingest.bq import report

    cfg = get_config(ctx.obj["config"])
    survey = json.loads((P.MANIFEST_DIR / "bq_cost_survey.json").read_text())
    est_path = P.MANIFEST_DIR / "hourly_download_estimate.json"
    est = json.loads(est_path.read_text()) if est_path.exists() else None
    today = datetime.now(UTC).date()
    md = report.render(
        survey,
        trusted_end=cfg.history.trusted_end,
        cutover=date.fromisoformat(cutover),
        budget=cfg.bigquery.monthly_budget_bytes,
        spent_first=int(spent_gb * 1e9),
        first_calendar_month=f"{today:%Y-%m}",
        hourly_estimate=est,
        generated=today,
    )
    out.write_text(md, encoding="utf-8")
    typer.echo(f"wrote {out}")


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
