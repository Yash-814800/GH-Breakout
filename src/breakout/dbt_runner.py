"""Run the dbt project with environment, caps and config-derived vars set (Phase 5)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml

from breakout import paths as P
from breakout.config import Config
from breakout.logging import get_logger

log = get_logger(__name__)

# GHB_DBT_DIR lets a long build run from a frozen copy of the project (edits to dbt/ would
# otherwise break the next bucket of a running job)
DBT_DIR = Path(os.environ.get("GHB_DBT_DIR") or P.ROOT / "dbt")
DERIVED_DIR = P.DERIVED_DIR
DEFAULT_MEMORY = "1500MB"


def dbt_env(
    base: dict[str, str] | None = None,
    *,
    lake: Path | None = None,
    derived: Path | None = None,
    warehouse: Path | None = None,
) -> dict[str, str]:
    """Environment for dbt: absolute paths, profiles dir and conservative resource caps."""
    env = dict(os.environ if base is None else base)
    env["DBT_PROFILES_DIR"] = str(DBT_DIR)
    env["GHB_LAKE"] = str((lake or P.LAKE_DIR).resolve())
    env["GHB_DERIVED"] = str((derived or DERIVED_DIR).resolve())
    env["GHB_WAREHOUSE"] = str(Path(warehouse or env.get("GHB_WAREHOUSE") or P.WAREHOUSE).resolve())
    env.setdefault("GHB_DUCKDB_MEMORY", DEFAULT_MEMORY)
    env.setdefault("GHB_DUCKDB_THREADS", "1")
    env.setdefault("GHB_DBT_THREADS", "1")
    env.setdefault("GHB_DUCKDB_TMP", str((P.TMP_DIR / "duckdb").resolve()))
    return env


def config_vars(cfg: Config) -> dict[str, Any]:
    """Vars that come from config/project.yaml."""
    return {
        "min_stars_14d": cfg.candidates.min_stars_14d,
        "max_age_days": cfg.candidates.max_age_days,
        "max_stars_total": cfg.candidates.max_stars_total,
        "exclude_forks": cfg.candidates.exclude_forks,
        "exclude_bot_owned": cfg.candidates.exclude_bot_owned,
        "horizon_days": cfg.labels.horizon_days,
        "relative_quantile": cfg.labels.relative_quantile,
        "relative_floor_gain": cfg.labels.relative_floor_gain,
        "absolute_min_gain": cfg.labels.absolute_min_gain,
        "first_snapshot": cfg.training.first_snapshot.isoformat(),
        "snapshot_weekday": cfg.training.snapshot_weekday,
        "session_gap_minutes": cfg.features.session_gap_minutes,
        "payload_trim_date": cfg.features.payload_trim_date.isoformat(),
        "tm_lookahead_days": cfg.features.tastemaker.lookahead_days,
        "tm_alpha": cfg.features.tastemaker.alpha,
        "tm_beta": cfg.features.tastemaker.beta,
        "tm_min_known": cfg.features.tastemaker.min_known,
        "tm_top_quantile": cfg.features.tastemaker.top_quantile,
        "hn_enabled": cfg.optional.hn_enabled,
        "detail_start_date": (cfg.history.detail_start_date or cfg.history.start_date).isoformat(),
    }


def history_vars(
    cfg: Config, start: date | None = None, end: date | None = None, n_buckets: int = 32
) -> dict[str, Any]:
    """Window of the full-history build: start of history to the end of the trusted era."""
    return {
        "events_start": (start or cfg.history.start_date).isoformat(),
        "events_end": (end or cfg.history.trusted_end + timedelta(days=1)).isoformat(),
        "n_buckets": n_buckets,
    }


def merge_vars(args: list[str], base: dict[str, Any]) -> list[str]:
    """Return ``args`` with ``--vars`` merged on top of ``base`` (user values win)."""
    out = list(args)
    merged = dict(base)
    for i, a in enumerate(out):
        if a == "--vars" and i + 1 < len(out):
            merged.update(yaml.safe_load(out[i + 1]) or {})
            del out[i : i + 2]
            break
        if a.startswith("--vars="):
            merged.update(yaml.safe_load(a.split("=", 1)[1]) or {})
            del out[i]
            break
    return [*out, "--vars", json.dumps(merged, default=str)]


# subcommands that do not accept --vars
_NO_VARS = {"deps", "clean", "init", "debug"}


def run_dbt(cfg: Config, args: list[str], *, extra_vars: dict[str, Any] | None = None) -> int:
    """Run ``dbt <args>`` from the repo root; returns the exit code."""
    (P.TMP_DIR / "duckdb").mkdir(parents=True, exist_ok=True)
    if args and args[0] not in _NO_VARS:
        args = merge_vars(args, {**config_vars(cfg), **(extra_vars or {})})
    cmd = [sys.executable, "-m", "dbt.cli.main", *args, "--project-dir", str(DBT_DIR)]
    log.info("dbt %s", " ".join(args))
    rc = subprocess.call(cmd, env=dbt_env(), cwd=P.ROOT)  # noqa: S603
    _collect_timings()
    return rc


TIMINGS: dict[str, float] = {}


def _collect_timings() -> None:
    """Add the execution time of every node of the last dbt call to TIMINGS (summed per node)."""
    f = DBT_DIR / "target" / "run_results.json"
    if f.exists():
        for r in json.loads(f.read_text())["results"]:
            TIMINGS[r["unique_id"]] = TIMINGS.get(r["unique_id"], 0.0) + r["execution_time"]


# Models too big for one statement under the memory cap: built one hash bucket per dbt call
# (ADR-020). Order matters inside each chain.
BUCKETED_A = ["stg_stars", "int_repo_star_daily", "int_star_active_repos"]
BUCKETED_B = [
    "int_actor_daily_activity",
    "int_actor_cumulative_activity",
    "int_star_events_enriched",
]
BUCKETED_A2 = ["int_active_repo_event_days"]  # 4 buckets: needs the scan of every event type
A2_BUCKETS = 4
BUCKETED_A3 = [  # 16 buckets: windows / joins over every event of the young-moving repos
    "int_repo_daily_activity",
    "int_contributor_sessions",
    "int_stargazer_later_actions",
]
A3_BUCKETS = 16
BUCKETED = [*BUCKETED_A, *BUCKETED_A2, *BUCKETED_A3, *BUCKETED_B]
SIGNALS = "stg_bot_actor_signals"


def _warehouse() -> Path:
    return Path(os.environ.get("GHB_WAREHOUSE") or P.WAREHOUSE)


def _done_buckets(model: str) -> set[int]:
    """Buckets already stored in ``model`` (empty when the table does not exist yet)."""
    wh = _warehouse()
    if not wh.exists():
        return set()
    import duckdb

    con = duckdb.connect(str(wh), read_only=True)
    try:
        return {r[0] for r in con.execute(f"select distinct bucket from {model}").fetchall()}
    except duckdb.Error:
        return set()
    finally:
        con.close()


def run_bucketed(cfg: Config, models: list[str], *, extra_vars: dict[str, Any]) -> int:
    """Build each model one bucket at a time, in order, resuming after the last stored bucket."""
    n = int(extra_vars.get("n_buckets", 32))
    for model in models:
        done = _done_buckets(model)
        for b in range(n):
            if b in done:
                continue
            args = ["run", "--select", model]
            if not done and b == 0:
                args.append("--full-refresh")
            log.info("bucket %d/%d of %s", b + 1, n, model)
            rc = run_dbt(cfg, args, extra_vars={**extra_vars, "bucket": b, "n_buckets": n})
            if rc != 0:
                return rc
    return 0


def run_history(
    cfg: Config,
    *,
    select: str = "known_bots staging intermediate",
    test: bool = True,
    start: date | None = None,
    end: date | None = None,
    n_buckets: int = 32,
    resume_at: str = "start",
) -> int:
    """Build staging + intermediate for all trusted history, then log timings and file size.

    ``resume_at='a3'`` skips every stage before the A3 bucketed models (already built).

    Stages: seed, bot signals by month chunk, bucketed chain A (stars), everything up to
    int_early_stars, bucketed chain B (actor activity), the rest, then tests of the bucketed models.
    """
    hv = history_vars(cfg, start, end, n_buckets)
    skip = [*BUCKETED, SIGNALS]
    cmd = "build" if test else "run"
    if resume_at == "start":
        if (rc := run_dbt(cfg, ["seed"])) != 0:  # signals reference the known_bots seed
            return rc
        if (rc := run_signals_in_chunks(cfg, hv)) != 0:
            return rc
        if (rc := run_dbt(cfg, ["run", "--select", "stg_bot_actors"], extra_vars=hv)) != 0:
            return rc
        if (rc := run_bucketed(cfg, BUCKETED_A, extra_vars=hv)) != 0:
            return rc
        if (
            rc := run_dbt(
                cfg,
                [cmd, "--select", "+int_early_stars", "stg_actor_age_map", "--exclude", *skip],
                extra_vars=hv,
            )
        ) != 0:
            return rc
    if (rc := run_bucketed(cfg, BUCKETED_A3, extra_vars={**hv, "n_buckets": A3_BUCKETS})) != 0:
        return rc
    if (rc := run_bucketed(cfg, BUCKETED_B, extra_vars=hv)) != 0:
        return rc
    rc = run_dbt(cfg, [cmd, "--select", *select.split(), "--exclude", *skip], extra_vars=hv)
    if test and rc == 0:
        rc = run_dbt(cfg, ["test", "--select", *BUCKETED, SIGNALS], extra_vars=hv)
    for uid, secs in sorted(TIMINGS.items(), key=lambda kv: -kv[1]):
        log.info("%-70s %9.1fs", uid, secs)
    if _warehouse().exists():
        log.info("warehouse size: %.2f GB", _warehouse().stat().st_size / 1e9)
    return rc


MARTS_CANDIDATES = ["mart_candidates"]
MARTS_TEST = ["mart_snapshot_dates", "mart_candidates", "mart_labels"]
# Phase 7 singular tests that also depend on the candidate marts need the feature tables, so the
# Phase 6 build excludes them (`breakout build features` runs them)
FEATURE_SINGULAR_TESTS = [
    "features_no_future_inputs",
    "features_star_windows_match_candidates",
    "features_tier_b_null_before_detail",
    "features_row_parity",
    "features_stg_stars_bucket_layout",
]


def run_labels(cfg: Config, *, test: bool = True, n_buckets: int = 32) -> int:
    """Snapshot dates, candidates (bucketed, resumable) and labels over the trusted history."""
    hv = history_vars(cfg, n_buckets=n_buckets)
    if (rc := run_dbt(cfg, ["run", "--select", "mart_snapshot_dates"], extra_vars=hv)) != 0:
        return rc
    if (rc := run_bucketed(cfg, MARTS_CANDIDATES, extra_vars=hv)) != 0:
        return rc
    rc = run_dbt(cfg, ["run", "--select", "mart_labels"], extra_vars=hv)
    if test and rc == 0:
        rc = run_dbt(
            cfg,
            ["test", "--select", *MARTS_TEST, "--exclude", *FEATURE_SINGULAR_TESTS],
            extra_vars=hv,
        )
    for uid, secs in sorted(TIMINGS.items(), key=lambda kv: -kv[1])[:8]:
        log.info("%-60s %9.1fs", uid, secs)
    return rc


def _signals_done_through() -> date | None:
    """Last month already present in stg_bot_actor_signals (None if the table is missing)."""
    wh = _warehouse()
    if not wh.exists():
        return None
    import duckdb

    con = duckdb.connect(str(wh), read_only=True)
    try:
        row = con.execute("select max(month) from stg_bot_actor_signals").fetchone()
    except duckdb.Error:
        return None
    finally:
        con.close()
    return row[0] if row else None


def run_signals_in_chunks(cfg: Config, hv: dict[str, Any], *, months_per_call: int = 3) -> int:
    """Build ``stg_bot_actor_signals`` a few months per dbt call (a big plan OOMs, ADR-020).

    Resumable: the first call full-refreshes only when the table is missing; later calls start after
    the last month already stored. Months are rebuilt delete+insert, so reruns never duplicate.
    """
    start = date.fromisoformat(hv["events_start"])
    end = date.fromisoformat(hv["events_end"])
    done = _signals_done_through()
    cur = date(start.year, start.month, 1)
    if done is not None:
        cur = max(cur, date(done.year + (done.month == 12), done.month % 12 + 1, 1))
    first = done is None
    while cur < end:
        y, m = cur.year, cur.month + months_per_call
        y, m = y + (m - 1) // 12, (m - 1) % 12 + 1
        nxt = min(date(y, m, 1), end)
        args = ["run", "--select", "stg_bot_actor_signals"] + (["--full-refresh"] if first else [])
        rc = run_dbt(
            cfg,
            args,
            extra_vars={"events_start": max(cur, start).isoformat(), "events_end": nxt.isoformat()},
        )
        if rc != 0:
            return rc
        first = False
        cur = nxt
    return 0
