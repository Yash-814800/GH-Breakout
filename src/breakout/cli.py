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

_STUBS: dict[str, int] = {}


def _make_stub(name: str, phase: int) -> typer.Typer:
    group = typer.Typer(help=f"{name} commands (Phase {phase}).", invoke_without_command=True)

    @group.callback()
    def _stub() -> None:
        typer.echo(f"{name}: not implemented yet (Phase {phase})")

    return group


for _name, _phase in _STUBS.items():
    app.add_typer(_make_stub(_name, _phase), name=_name)

daily_app = typer.Typer(help="Daily pipeline commands (Phase 9).", no_args_is_help=True)
app.add_typer(daily_app, name="daily")

ops_app = typer.Typer(help="Operations and parity commands (Phase 9).", no_args_is_help=True)
app.add_typer(ops_app, name="ops")

publish_app = typer.Typer(help="Publish and deployment commands (Phase 9+).", no_args_is_help=True)
app.add_typer(publish_app, name="publish")

detect_app = typer.Typer(
    help="Fake-star detection, similarity, and cohorts (Phase 11).", no_args_is_help=True
)
app.add_typer(detect_app, name="detect")

ml_app = typer.Typer(help="Modelling and evaluation (Phase 6+).", no_args_is_help=True)
app.add_typer(ml_app, name="ml")


@ml_app.command("baseline")
def ml_baseline_cmd(
    ctx: typer.Context,
    n_boot: Annotated[int, typer.Option(help="bootstrap resamples for the CIs")] = 1000,
    labels_file: Annotated[
        Path | None, typer.Option(help="exported candidates_labels.parquet")
    ] = None,
) -> None:
    """Score the velocity baselines on the rolling-origin folds; write reports/baseline.md."""
    from breakout.ml import baseline

    cfg = get_config(ctx.obj["config"])
    baseline.run(cfg, labels_file, n_boot=n_boot)
    typer.echo(f"wrote {baseline.REPORT}")


@ml_app.command("cv")
def ml_cv_cmd(
    ctx: typer.Context,
    variant: Annotated[
        list[str] | None, typer.Option("--variant", help="CV variant(s); default: full")
    ] = None,
    fold: Annotated[
        list[int] | None, typer.Option("--fold", help="only these fold numbers")
    ] = None,
    report: Annotated[bool, typer.Option(help="write reports/model_cv.md from the shards")] = False,
    n_boot: Annotated[
        int | None, typer.Option(help="bootstrap resamples (default: config)")
    ] = None,
) -> None:
    """Rolling-origin CV of the LightGBM model (resumable); ``--report`` renders the report."""
    from breakout.ml import cv

    cfg = get_config(ctx.obj["config"])
    if report:
        from breakout.ml import cv_report

        cv_report.run(cfg, n_boot=n_boot)
        typer.echo(f"wrote {cv_report.REPORT}")
        return
    cv.run(cfg, variant or ["full"], fold)
    typer.echo("ok")


@ml_app.command("train-final")
def ml_train_final_cmd(
    ctx: typer.Context,
    candidate: Annotated[
        bool, typer.Option("--candidate", help="train as candidate rather than directly promoting")
    ] = False,
    monotone: Annotated[
        bool | None, typer.Option(help="monotone constraints (default: the CV decision)")
    ] = None,
) -> None:
    """Train + holdout-evaluate, package data/models/<version>/ and apply the promotion rule."""
    from breakout.ml import final

    cfg = get_config(ctx.obj["config"])
    res = final.train_final(cfg, monotone=monotone, candidate=candidate)
    typer.echo(json.dumps(res, indent=2))


@ml_app.command("promote")
def ml_promote_cmd(
    ctx: typer.Context,
    candidate: Annotated[
        str | None,
        typer.Option("--candidate", help="candidate version (default: latest unpromoted)"),
    ] = None,
    if_better: Annotated[
        bool, typer.Option("--if-better", help="only promote if candidate beats B1 and champion")
    ] = True,
    upload: Annotated[
        bool, typer.Option("--upload", help="push the candidate, champion and registry to the Hub")
    ] = False,
) -> None:
    """Promote candidate model to champion if holdout rule passes."""
    from breakout.ml import final
    from breakout.ml import registry as reg_mod

    cfg = get_config(ctx.obj["config"])
    res = final.promote_candidate(cfg, version=candidate, if_better=if_better)
    if upload:
        for v in dict.fromkeys([res["candidate"], res["champion"]]):
            reg_mod.upload_version(cfg, v)
    typer.echo(json.dumps(res, indent=2))


@ml_app.command("append-live-training")
def ml_append_live_training_cmd(
    ctx: typer.Context,
    upload: Annotated[
        bool, typer.Option("--upload", help="upload appended live files to derived repo")
    ] = False,
) -> None:
    """Append newly matured live Monday predictions to the training dataset."""
    from breakout.ml import append_live

    cfg = get_config(ctx.obj["config"])
    res = append_live.append_live_training(cfg, upload=upload)
    typer.echo(json.dumps(res, indent=2))


@ml_app.command("explain")
def ml_explain_cmd(
    ctx: typer.Context, version: Annotated[str, typer.Option(help="model version")]
) -> None:
    """Global SHAP figures (reports/figures) of a packaged model."""
    from breakout.ml import final

    res = final.explain_figures(get_config(ctx.obj["config"]), version)
    top = list(res["importance"].items())[:10]
    typer.echo(json.dumps({"files": res["files"], "top10": top}, indent=1))


@ml_app.command("predict")
def ml_predict_cmd(
    ctx: typer.Context,
    date_: Annotated[str, typer.Option("--date", help="snapshot date D (YYYY-MM-DD)")],
    top: Annotated[int, typer.Option(help="rows to print")] = 10,
    features_file: Annotated[str | None, typer.Option(help="live features parquet")] = None,
) -> None:
    """Score a live features file with the champion and print the top rows with explanations."""
    from breakout.ml import final

    cfg = get_config(ctx.obj["config"])
    out = final.predict_date(cfg, date_, top, features_file)
    for i, r in out.iterrows():
        typer.echo(f"{i + 1:>2}. {r['repo']}  p={r['prob']:.3%}  (score {r['raw_score']:.4f})")
        typer.echo(f"    {r['explanation']}")
    typer.echo(f"model {out['model_version'].iloc[0]}")


build_app = typer.Typer(help="dbt build commands (Phase 5).", no_args_is_help=True)
app.add_typer(build_app, name="build")


@build_app.command(
    "dbt",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def build_dbt_cmd(ctx: typer.Context) -> None:
    """Run dbt with paths, caps and config vars set: ``breakout build dbt -- run --select x``."""
    from breakout.dbt_runner import run_dbt

    cfg = get_config(ctx.obj["config"])
    raise typer.Exit(run_dbt(cfg, list(ctx.args)))


@build_app.command("history")
def build_history_cmd(
    ctx: typer.Context,
    select: Annotated[str, typer.Option(help="dbt selector")] = "known_bots staging intermediate",
    test: Annotated[bool, typer.Option(help="run tests too (dbt build)")] = True,
    start: Annotated[str | None, typer.Option(help="window start (default: history start)")] = None,
    end: Annotated[
        str | None, typer.Option(help="window end, exclusive (default: trusted end)")
    ] = None,
    buckets: Annotated[int, typer.Option(help="hash buckets of the big models")] = 32,
    resume_at: Annotated[
        str, typer.Option(help="start | a3 (skip stages already built)")
    ] = "start",
) -> None:
    """Full-history build of staging + intermediate over the trusted era; logs time per model."""
    from breakout.dbt_runner import run_history

    cfg = get_config(ctx.obj["config"])
    from datetime import date

    raise typer.Exit(
        run_history(
            cfg,
            select=select,
            test=test,
            start=date.fromisoformat(start) if start else None,
            end=date.fromisoformat(end) if end else None,
            n_buckets=buckets,
            resume_at=resume_at,
        )
    )


@build_app.command("labels")
def build_labels_cmd(
    ctx: typer.Context,
    test: Annotated[bool, typer.Option(help="run the mart tests")] = True,
    build: Annotated[bool, typer.Option(help="run dbt (off = export only)")] = True,
    upload: Annotated[bool, typer.Option(help="upload the export to the derived repo")] = False,
) -> None:
    """Build snapshot dates, candidates and labels (dbt), export to Parquet, print the summary."""
    from breakout.dbt_runner import run_labels
    from breakout.ml import labels_export as le

    cfg = get_config(ctx.obj["config"])
    if build and (rc := run_labels(cfg, test=test)) != 0:
        raise typer.Exit(rc)
    summary = le.export_labels()
    typer.echo(json.dumps(summary, indent=2, default=str))
    if upload:
        typer.echo(json.dumps(le.upload_labels(cfg)))


@ml_app.command("daily-check")
def ml_daily_check_cmd(
    ctx: typer.Context,
    version: Annotated[str, typer.Option(help="model version under data/models")],
    start: Annotated[str | None, typer.Option(help="first day (build + export)")] = None,
    end: Annotated[str | None, typer.Option(help="last day, inclusive (build + export)")] = None,
    build: Annotated[
        bool, typer.Option(help="dbt-build the daily range (warehouse COPY!)")
    ] = False,
    buckets: Annotated[int, typer.Option(help="repo_id hash buckets")] = 32,
) -> None:
    """Daily-vs-weekly check: build (optional), export, score and write daily_check.json."""
    from datetime import date as _date

    from breakout.features import build as fb
    from breakout.ml import daily_check as dc

    cfg = get_config(ctx.obj["config"])
    if build:
        if not (start and end):
            raise typer.BadParameter("--build needs --start and --end")
        rc = fb.run_features_range(
            cfg, _date.fromisoformat(start), _date.fromisoformat(end), n_buckets=buckets
        )
        if rc != 0:
            raise typer.Exit(rc)
    if start and end:
        dc.export_range(fb.warehouse_path(), _date.fromisoformat(start), _date.fromisoformat(end))
    typer.echo(f"wrote {dc.run(cfg, version)}")


@build_app.command("features")
def build_features_cmd(
    ctx: typer.Context,
    history: Annotated[
        bool, typer.Option("--history", help="weekly snapshots, trusted history")
    ] = False,
    date_: Annotated[str | None, typer.Option("--date", help="single live snapshot date")] = None,
    test: Annotated[bool, typer.Option(help="run the dbt tests of the feature models")] = True,
    build: Annotated[bool, typer.Option(help="run dbt (off = export only)")] = True,
    full_refresh: Annotated[bool, typer.Option(help="drop and rebuild the feature tables")] = False,
    buckets: Annotated[int, typer.Option(help="repo_id hash buckets")] = 32,
    export: Annotated[bool, typer.Option(help="export the training / live Parquet files")] = True,
    upload: Annotated[bool, typer.Option(help="upload training/ to the derived repo")] = False,
    window_start: Annotated[str | None, typer.Option(help="--date: events window start")] = None,
    window_end: Annotated[
        str | None, typer.Option(help="--date: events window end (exclusive)")
    ] = None,
) -> None:
    """Point-in-time feature marts: --history (training table) or --date D (live features)."""
    from datetime import date as _date

    from breakout.features import build as fb

    if history == (date_ is not None):
        raise typer.BadParameter("pass exactly one of --history and --date YYYY-MM-DD")
    cfg = get_config(ctx.obj["config"])
    if history:
        if (
            build
            and (
                rc := fb.run_features(cfg, n_buckets=buckets, test=test, full_refresh=full_refresh)
            )
            != 0
        ):
            raise typer.Exit(rc)
        if export:
            manifest = fb.export_training(cfg)
            typer.echo(
                json.dumps(
                    {k: manifest[k] for k in ("rows_total", "rows_per_year", "dbt_git_sha")},
                    indent=2,
                )
            )
        if upload:
            from breakout.features import publish

            typer.echo(json.dumps(publish.upload_training(cfg)))
        return
    d = _date.fromisoformat(date_)  # type: ignore[arg-type]
    window = (
        (_date.fromisoformat(window_start), _date.fromisoformat(window_end))
        if window_start and window_end
        else None
    )
    if build and (rc := fb.run_features_single(cfg, d, window=window)) != 0:
        raise typer.Exit(rc)
    out = fb.export_live(d)
    ok, msg = fb.schemas_match(out)
    typer.echo(f"wrote {out}; schema vs training table: {'OK' if ok else 'MISMATCH'}: {msg}")
    if not ok:
        raise typer.Exit(1)


@build_app.command("leak-test")
def build_leak_test_cmd(
    ctx: typer.Context,
    date_: Annotated[list[str], typer.Option("--date", help="snapshot date (repeat for several)")],
    sample: Annotated[int, typer.Option(help="candidates sampled per date")] = 300,
    warehouse: Annotated[Path | None, typer.Option(help="warehouse holding the date")] = None,
) -> None:
    """Time-travel test: features at D from inputs truncated at D must equal the normal ones."""
    from datetime import date as _date

    from breakout.features import leak

    cfg = get_config(ctx.obj["config"])
    failed = False
    for ds in date_:
        res = leak.run_leak_test(cfg, _date.fromisoformat(ds), sample, warehouse)
        typer.echo(res.summary())
        for diff in res.differences:
            typer.echo(f"  DIFF {diff}")
        failed |= not res.passed
    raise typer.Exit(1 if failed else 0)


@build_app.command("feature-eda")
def build_feature_eda_cmd(ctx: typer.Context) -> None:
    """Write reports/feature_eda.md (+ small PNGs) from the exported training table."""
    from breakout.features import eda

    cfg = get_config(ctx.obj["config"])
    typer.echo(f"wrote {eda.run(cfg)}")


@build_app.command("state")
def build_state_cmd(
    ctx: typer.Context,
    as_of: Annotated[str, typer.Option("--as-of", help="cutoff date YYYY-MM-DD")],
    upload: Annotated[bool, typer.Option("--upload", help="upload to derived repo")] = False,
) -> None:
    """Initialize persistent state tables (tastemaker, owner, thresholds) as of date."""
    from datetime import date

    from breakout.features import state

    cfg = get_config(ctx.obj["config"])
    p1, p2, p3 = state.build_state(cfg, date.fromisoformat(as_of), upload=upload)
    typer.echo(f"Built state tables:\n  {p1}\n  {p2}\n  {p3}")


enrich_app = typer.Typer(
    help="Enrichment: names, repo metadata, actor age, trending, HN.", no_args_is_help=True
)
app.add_typer(enrich_app, name="enrich")

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


@lake_app.command("verify-remote")
def lake_verify_remote_cmd(ctx: typer.Context) -> None:
    """Check the Hub against its own catalog (no local lake needed); exit 1 on violations."""
    from breakout.lake import hf, sync
    from breakout.lake.verify import verify_remote

    cfg = get_config(ctx.obj["config"])
    api = hf.get_api()
    remote, _ = sync.fetch_remote_catalog(api, cfg)
    rows = remote.to_pylist()
    typer.echo(
        f"{len(rows)} files, {sum(r['bytes'] for r in rows) / 1e9:.2f} GB, "
        f"{sum(r['rows'] for r in rows):,} rows"
    )
    problems = verify_remote(cfg, api, remote.slice(0, 0))
    typer.echo(f"remote: {len(problems)} problem(s)")
    for line in problems[:50]:
        typer.echo(f"  - {line}")
    if problems:
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


def _gh_api(cfg):
    """Throttled GitHub API caller; the token comes from the environment and is never echoed."""
    from breakout.enrich import http as H

    token = os.environ.get("GH_ENRICH_TOKEN", "")
    if not token:
        typer.echo("GH_ENRICH_TOKEN is not set", err=True)
        raise typer.Exit(2)
    client = H.make_client(cfg.enrich.repo_url)
    return H.GitHubApi(token, client=client, max_rps=cfg.enrich.max_rps)


def _stop_flag():
    import signal

    flag = {"stop": False}

    def handler(signum, frame):  # noqa: ARG001
        flag["stop"] = True

    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)
    return lambda: flag["stop"]


@enrich_app.command("names")
def enrich_names_cmd(ctx: typer.Context) -> None:
    """Build enrich/repo_name_history.parquet from the local WatchEvent lake."""
    from breakout.enrich import names

    cfg = get_config(ctx.obj["config"])
    _require_lake(cfg)
    typer.echo(json.dumps(names.build_name_history(cfg)))


@enrich_app.command("targets")
def enrich_targets_cmd(ctx: typer.Context) -> None:
    """Compute the metadata target set (trusted era) into repo_targets.parquet."""
    from breakout.enrich import github_meta

    cfg = get_config(ctx.obj["config"])
    _require_lake(cfg)
    typer.echo(json.dumps(github_meta.build_targets(cfg)))


@enrich_app.command("repos")
def enrich_repos_cmd(
    ctx: typer.Context,
    repo_ids_file: Annotated[Path | None, typer.Option("--repo-ids-file")] = None,
    limit: Annotated[int | None, typer.Option(help="max repos to fetch this run")] = None,
    max_age_days: Annotated[int | None, typer.Option("--max-age-days")] = None,
) -> None:
    """Fetch GitHub metadata for the target set (incremental: fresh rows are skipped)."""
    from breakout.enrich import github_meta

    cfg = get_config(ctx.obj["config"])
    api = _gh_api(cfg)
    stats = github_meta.run_fetch(
        cfg,
        api,
        repo_ids_file=repo_ids_file,
        limit=limit,
        max_age_days=max_age_days,
        should_stop=_stop_flag(),
    )
    typer.echo(json.dumps({**stats.as_dict(), "http_requests": api.requests}))


@enrich_app.command("actor-age")
def enrich_actor_age_cmd(
    ctx: typer.Context,
    samples: Annotated[int | None, typer.Option(help="number of sampled actor ids")] = None,
    skip_fetch: Annotated[bool, typer.Option("--skip-fetch")] = False,
) -> None:
    """Sample actor ids, fetch account creation dates, fit the isotonic id -> age map."""
    from breakout.enrich import actor_age

    cfg = get_config(ctx.obj["config"])
    n = samples or cfg.enrich.actor_samples
    if not skip_fetch:
        _require_lake(cfg)
        ids = actor_age.pick_sample_ids(cfg, n)
        api = _gh_api(cfg)
        typer.echo(json.dumps(actor_age.collect_samples(cfg, api, ids, should_stop=_stop_flag())))
    typer.echo(json.dumps(actor_age.build_map(cfg), default=str))


@enrich_app.command("trending-history")
def enrich_trending_history_cmd(ctx: typer.Context) -> None:
    """Union the archived trending sources and resolve repo ids."""
    from breakout.enrich import trending

    cfg = get_config(ctx.obj["config"])
    res = trending.build_trending(cfg, trending.history_rows(cfg))
    typer.echo(json.dumps(res))


@enrich_app.command("trending-today")
def enrich_trending_today_cmd(ctx: typer.Context) -> None:
    """Fetch today's GitHub trending list (robots.txt checked) and merge it."""
    from datetime import UTC, datetime

    from breakout.enrich import http as H
    from breakout.enrich import trending

    cfg = get_config(ctx.obj["config"])
    today = datetime.now(UTC).date()
    with H.make_client(cfg.enrich.repo_url) as client:
        rows = trending.trending_today(cfg, client, today)
    if not rows:
        typer.echo("no rows fetched (robots.txt disallows or empty page); archives unchanged")
        return
    import pyarrow.parquet as pq

    from breakout.enrich.common import enrich_dir

    path = enrich_dir(cfg) / trending.TRENDING
    base = pq.read_table(path).to_pylist() if path.exists() else []
    base = [r for r in base if not (r["source"] == "github_trending" and r["date"] == today)]
    res = trending.build_trending(cfg, [*base, *rows])
    typer.echo(json.dumps(res))


def _hn_client(cfg):
    from breakout.enrich import hn
    from breakout.enrich import http as H

    return hn.HnClient(H.make_client(cfg.enrich.repo_url), max_rps=cfg.enrich.max_rps)


@enrich_app.command("hn-history")
def enrich_hn_history_cmd(
    ctx: typer.Context,
    since: Annotated[str | None, typer.Option(help="YYYY-MM-DD")] = None,
) -> None:
    """Fetch HN stories linking to github.com from ``--since`` (resumable by window)."""
    from datetime import UTC, date, datetime

    from breakout.enrich import hn

    cfg = get_config(ctx.obj["config"])
    if not cfg.optional.hn_enabled:
        typer.echo("optional.hn_enabled is false; nothing to do")
        return
    start = date.fromisoformat(since) if since else cfg.enrich.hn_start
    res = hn.collect(cfg, _hn_client(cfg), start, datetime.now(UTC).replace(tzinfo=None))
    typer.echo(json.dumps(res))
    typer.echo(json.dumps(hn.build_stories(cfg), default=str))


@enrich_app.command("hn-recent")
def enrich_hn_recent_cmd(ctx: typer.Context, days: Annotated[int, typer.Option(min=1)] = 3) -> None:
    """Refetch the last ``days`` days (points keep changing) and rebuild the stories table."""
    from datetime import UTC, datetime

    from breakout.enrich import hn

    cfg = get_config(ctx.obj["config"])
    if not cfg.optional.hn_enabled:
        typer.echo("optional.hn_enabled is false; nothing to do")
        return
    start = hn.recent_start(days)
    res = hn.collect(
        cfg,
        _hn_client(cfg),
        start.date(),
        datetime.now(UTC).replace(tzinfo=None),
        refetch_from=start,
    )
    typer.echo(json.dumps(res))
    typer.echo(json.dumps(hn.build_stories(cfg), default=str))


@enrich_app.command("upload")
def enrich_upload_cmd(ctx: typer.Context) -> None:
    """Upload enrich/*.parquet to the derived HF repo (skips unchanged files)."""
    from breakout.enrich import upload

    cfg = get_config(ctx.obj["config"])
    typer.echo(json.dumps(upload.upload_enrich(cfg)))


# ---- Daily (Phase 9) ---------------------------------------------------------


@daily_app.command("run")
def daily_run_cmd(
    ctx: typer.Context,
    date_: Annotated[
        str | None, typer.Option("--date", help="snapshot date (YYYY-MM-DD), default today UTC")
    ] = None,
    skip_deploy_data: Annotated[
        bool, typer.Option("--skip-deploy-data", help="skip publishing site data")
    ] = False,
    no_commit: Annotated[
        bool, typer.Option("--no-commit", help="skip git commit of ledger and status")
    ] = False,
    no_upload: Annotated[
        bool, typer.Option("--no-upload", help="skip Hugging Face uploads (reads still happen)")
    ] = False,
    skip_bootstrap: Annotated[
        bool, typer.Option("--skip-bootstrap", help="do not pull missing inputs from the Hub")
    ] = False,
) -> None:
    """Run the 15-step daily pipeline."""
    from datetime import date

    from breakout.daily import run as daily_run

    cfg = get_config(ctx.obj["config"])
    d = date.fromisoformat(date_) if date_ else None
    rc = daily_run.daily_run(
        cfg,
        d=d,
        skip_deploy_data=skip_deploy_data,
        no_commit=no_commit,
        no_upload=no_upload,
        skip_bootstrap=skip_bootstrap,
    )
    if rc != 0:
        raise typer.Exit(rc)


# ---- Ops (Phase 9) -----------------------------------------------------------


@ops_app.command("verify-ledger")
def ops_verify_ledger_cmd(
    ctx: typer.Context,
    remote: Annotated[
        bool, typer.Option("--remote", help="verify against remote HF snapshots")
    ] = False,
) -> None:
    """Verify hash chain integrity of the immutable predictions ledger."""
    from breakout.ops import ledger

    cfg = get_config(ctx.obj["config"])
    ok, msg = ledger.verify_ledger(cfg, remote=remote)
    typer.echo(msg)
    if not ok:
        raise typer.Exit(1)


@ops_app.command("parity")
def ops_parity_cmd(
    ctx: typer.Context,
    date_: Annotated[str, typer.Option("--date", help="snapshot date D0 (YYYY-MM-DD)")],
) -> None:
    """Run training/serving parity test comparing window mode against history mart."""
    from datetime import date

    from breakout.ops import parity

    cfg = get_config(ctx.obj["config"])
    res = parity.run_parity(cfg, date.fromisoformat(date_))
    typer.echo(f"Parity result for {res.snapshot_date}: {'PASS' if res.passed else 'FAIL'}")
    typer.echo(f"  Jaccard: {res.jaccard:.4f}")
    typer.echo(f"  Cell match: {res.overall_cell_match_rate:.4%}")
    typer.echo(f"  Rank corr: {res.spearman_rank_corr:.4f}")
    typer.echo(f"Report: {res.report_path}")
    if not res.passed:
        raise typer.Exit(1)


@ops_app.command("bootstrap-weekly")
def ops_bootstrap_weekly_cmd(ctx: typer.Context) -> None:
    """Pull training rows, labels, live features and the registry onto a clean runner."""
    from breakout.daily import bootstrap

    typer.echo(json.dumps(bootstrap.bootstrap_weekly(get_config(ctx.obj["config"])), indent=2))


@ops_app.command("drift")
def ops_drift_cmd(
    ctx: typer.Context,
    upload: Annotated[
        bool, typer.Option("--upload", help="upload drift.json to derived repo")
    ] = False,
) -> None:
    """Compute PSI drift over recent live features vs champion training."""
    from breakout.ops import drift

    cfg = get_config(ctx.obj["config"])
    res = drift.compute_drift(cfg, upload=upload)
    typer.echo(json.dumps(res, indent=2))
    if res.get("status") == "drift_detected":
        typer.echo("WARNING: Significant feature drift detected (PSI > 0.25)")


# ---- Publish (Phase 9/10) ----------------------------------------------------


@publish_app.command("site-data")
def publish_site_data_cmd(
    ctx: typer.Context,
    date_: Annotated[
        str | None, typer.Option("--date", help="snapshot date (default: latest prediction)")
    ] = None,
    upload: Annotated[
        bool,
        typer.Option(
            "--upload",
            help="Upload site data to derived repo under site_data/latest/",
        ),
    ] = False,
) -> None:
    """Export site data (leaderboard, details, track record, backtest, status, explorer)."""
    from datetime import date

    from breakout.publish import site_data

    cfg = get_config(ctx.obj["config"])
    d = date.fromisoformat(date_) if date_ else None
    p1, p2 = site_data.publish_site_data(cfg, d, upload=upload)
    typer.echo(f"Wrote site data:\n  {p1}\n  {p2}")


@publish_app.command("insights")
def publish_insights_cmd(
    ctx: typer.Context,
) -> None:
    """Export historical data stories to site/public/data/insights.json (Phase 11, §11.4)."""
    from breakout.publish import insights

    p = insights.export_insights_data()
    typer.echo(f"Wrote insights stories to {p}")


@publish_app.command("dbt-docs")
def publish_dbt_docs_cmd(
    ctx: typer.Context,
    refresh_catalog: Annotated[
        bool,
        typer.Option(
            "--refresh-catalog",
            help="read column types from the local warehouse and rewrite reports/dbt/catalog.json",
        ),
    ] = False,
) -> None:
    """Generate the dbt docs and copy them to site/public/dbt-docs/ (Phase 13.2)."""
    from breakout.publish import dbt_docs

    cfg = get_config(ctx.obj["config"])
    typer.echo(f"Wrote {dbt_docs.publish_docs(cfg, refresh_catalog=refresh_catalog)}")


@publish_app.command("data-dictionary")
def publish_data_dictionary_cmd(ctx: typer.Context) -> None:
    """Write docs/data_dictionary.md from the dbt manifest (Phase 13.2)."""
    from breakout.publish import dbt_docs

    cfg = get_config(ctx.obj["config"])
    typer.echo(f"Wrote {dbt_docs.write_data_dictionary(cfg)}")


@publish_app.command("feeds")
def publish_feeds_cmd(ctx: typer.Context) -> None:
    """Write feed_items.json (new leaderboard entries) for /feed.xml and /feed.json (Phase 12.1)."""
    from breakout.publish import distribution

    cfg = get_config(ctx.obj["config"])
    distribution.restore_snapshots(cfg)
    typer.echo(f"Wrote {distribution.export_feed_items(cfg)}")


@publish_app.command("badges")
def publish_badges_cmd(ctx: typer.Context) -> None:
    """Write shields.io endpoint badges for every repo flagged in the last 90 days (Phase 12.2)."""
    from breakout.publish import distribution

    cfg = get_config(ctx.obj["config"])
    distribution.restore_snapshots(cfg)
    written = distribution.export_badges(cfg)
    typer.echo(f"Wrote {len(written)} badge files to {distribution.BADGES_DIR}")


@publish_app.command("digest")
def publish_digest_cmd(
    ctx: typer.Context,
    week: Annotated[
        str | None,
        typer.Option("--week", help="ISO week, e.g. 2026-W43 (default: the last complete week)"),
    ] = None,
    upload: Annotated[
        bool, typer.Option("--upload", help="store the digest on the derived repo (digests/)")
    ] = False,
) -> None:
    """Generate the weekly digest from frozen snapshots and outcomes (Phase 12.3)."""
    from breakout.publish import distribution

    cfg = get_config(ctx.obj["config"])
    wk = week or distribution.default_week()
    distribution.restore_snapshots(cfg, outcomes=True)
    distribution.pull_site_facts(cfg)
    doc = distribution.build_digest(cfg, wk)
    p = distribution.write_digest(doc)
    typer.echo(f"Wrote {p}\n{doc['summary']}")
    if upload:
        distribution.upload_digests(cfg)
        typer.echo("Uploaded digests/ to the derived repo")


@publish_app.command("discuss-digest")
def publish_discuss_digest_cmd(
    ctx: typer.Context,
    week: Annotated[
        str | None, typer.Option("--week", help="ISO week (default: last complete)")
    ] = None,
    repo: Annotated[
        str, typer.Option("--repo", help="owner/name of the repository with Discussions")
    ] = "Yash-814800/GH-Breakout",
    category: Annotated[str, typer.Option("--category")] = "Digest",
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    """Post the weekly digest as a GitHub Discussion (Phase 12.5). Token from GITHUB_TOKEN."""
    from breakout.publish import distribution

    wk = week or distribution.default_week()
    p = distribution.DIGESTS_DIR / f"{wk}.json"
    if not p.exists():
        typer.echo(f"No digest file for {wk}; run `breakout publish digest --week {wk}` first")
        raise typer.Exit(1)
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    if not token and not dry_run:
        typer.echo("GITHUB_TOKEN is not set")
        raise typer.Exit(1)
    res = distribution.post_discussion(
        json.loads(p.read_text()), repo=repo, token=token, category=category, dry_run=dry_run
    )
    typer.echo(json.dumps({k: v for k, v in res.items() if k != "body"}, indent=2))
    if dry_run:
        typer.echo(res["body"])


# ---- Detect (Phase 11) -------------------------------------------------------


@detect_app.command("suspicion")
def detect_suspicion_cmd(
    ctx: typer.Context,
    date_: Annotated[
        str | None, typer.Option("--date", help="snapshot date (default: latest)")
    ] = None,
    limit: Annotated[int, typer.Option("--limit", help="number of top suspicious to display")] = 20,
) -> None:
    """Compute suspicious-growth scores and display top flagged candidates."""
    from datetime import date

    from breakout.detect import scoring, signals
    from breakout.duck import connect

    wh = P.DATA_DIR / "warehouse.duckdb"
    if not wh.exists():
        typer.echo(f"Warehouse not found at {wh}")
        raise typer.Exit(1)

    con = connect(wh, read_only=True)
    try:
        snap_d = date.fromisoformat(date_) if date_ else None
        if snap_d is None:
            row = con.execute("select max(snapshot_date) from mart_candidates").fetchone()
            snap_d = row[0] if (row and row[0]) else date.today()

        df = signals.extract_candidate_signals(con, target_date=snap_d)
        if df.empty:
            typer.echo(f"No candidates found for snapshot date {snap_d}")
            return

        z_df = scoring.compute_signals_zscores(df)
        raw = scoring.compute_weighted_raw_score(z_df)
        cdf = scoring.map_empirical_cdf(raw)
        z_df["suspicion_score"] = cdf
        z_df["suspicion_level"] = [scoring.classify_suspicion_level(s) for s in cdf]

        top = z_df.sort_values("suspicion_score", ascending=False).head(limit)
        typer.echo(
            f"Top {len(top)} suspicious candidates on {snap_d} (total candidates: {len(df)}):"
        )
        for _, r in top.iterrows():
            reasons = scoring.format_reason_codes(r)
            r_str = f" - {'; '.join(reasons)}" if reasons else ""
            lvl = r["suspicion_level"].upper()
            name = r.get("repo_name", r["repo_id"])
            typer.echo(f"  [{lvl}] {name} (score: {r['suspicion_score']:.1f}){r_str}")
    finally:
        con.close()


@detect_app.command("similarity-reference")
def detect_similarity_ref_cmd(
    ctx: typer.Context,
    as_of: Annotated[
        str | None, typer.Option("--as-of", help="as-of date (default: latest)")
    ] = None,
    window_days: Annotated[int, typer.Option("--window-days", help="lookback window days")] = 365,
    min_stars: Annotated[int, typer.Option("--min-stars", help="min stars in window")] = 50,
) -> None:
    """Build similarity reference index from recent WatchEvents (weekly job)."""
    from datetime import date

    from breakout.detect import similarity

    cfg = get_config(ctx.obj["config"])
    as_of_date = date.fromisoformat(as_of) if as_of else None
    p1, p2, stats = similarity.build_similarity_reference(
        cfg, as_of=as_of_date, window_days=window_days, min_stars=min_stars
    )
    typer.echo("Similarity reference built:")
    typer.echo(f"  Stargazers: {p1} ({stats['stargazers_parquet_mb']:.2f} MB)")
    typer.echo(f"  Repo sizes: {p2} ({stats['sizes_parquet_mb']:.2f} MB)")
    n_repos = stats["n_reference_repos"]
    n_pairs = stats["n_reference_stargazer_pairs"]
    duration = stats["duration_seconds"]
    typer.echo(f"  Indexed {n_repos} repos ({n_pairs} pairs) in {duration}s")


@detect_app.command("cohorts-reference")
def detect_cohorts_ref_cmd(
    ctx: typer.Context,
) -> None:
    """Precompute historical retention reference band for breakout_rel positives."""
    from breakout.detect import cohorts

    p = cohorts.compute_retention_reference()
    typer.echo(f"Wrote retention reference band to {p}")


@detect_app.command("validate")
def detect_validate_cmd(
    ctx: typer.Context,
    output: Annotated[Path | None, typer.Option("--output", help="output report path")] = None,
) -> None:
    """Run StarScout validation, spotcheck, and ablation; write reports/suspicion.md."""
    from breakout.detect import validate

    p = validate.generate_suspicion_report(output_path=output)
    typer.echo(f"Generated suspicion validation report at {p}")


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
