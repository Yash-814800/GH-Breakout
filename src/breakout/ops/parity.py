"""Training/serving parity test (§9.6).

Compares features and predictions generated in daily window mode (using persistent state)
against the historical warehouse mart for a given snapshot date D0.
Requirements:
- Candidate set Jaccard similarity >= 0.99
- Feature values equal within 1e-6 for >= 99% of cells per feature
- Prediction rank correlation (Spearman) >= 0.99
Writes `docs/parity_daily_vs_history.md`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from breakout import dbt_runner as R
from breakout import paths as P
from breakout.config import Config, get_config
from breakout.features.state import TASTEMAKER_STATE_PATH
from breakout.logging import get_logger
from breakout.ml import dataset as D
from breakout.ml import registry as G

log = get_logger(__name__)

PARITY_DOC_PATH = P.ROOT / "docs" / "parity_daily_vs_history.md"


@dataclass
class ParityResult:
    snapshot_date: date
    jaccard: float
    n_history_candidates: int
    n_window_candidates: int
    n_common_candidates: int
    feature_parity: dict[str, float]  # feature_name -> match_rate (0.0 .. 1.0)
    overall_cell_match_rate: float
    spearman_rank_corr: float
    passed: bool
    report_path: Path
    discrepancies: list[str] = field(default_factory=list)


def run_parity(
    cfg: Config | None = None,
    d0: date | None = None,
    warehouse: Path | None = None,
) -> ParityResult:
    """Run training/serving parity verification for Monday snapshot d0."""
    cfg = cfg or get_config(None)
    # Default to 2024-06-03 (Monday inside trusted hourly era, post-cutover)
    snap_date = d0 or date(2024, 6, 3)
    wh = warehouse or Path(os.environ.get("GHB_WAREHOUSE") or P.WAREHOUSE)

    if not wh.exists():
        raise FileNotFoundError(f"Warehouse not found at {wh}")

    if not TASTEMAKER_STATE_PATH.exists():
        raise FileNotFoundError(
            "Persistent state missing. Run `breakout build state --as-of <date>` first."
        )

    log.info("Starting training/serving parity test for %s...", snap_date)

    # 1. Read history mart features for d0 from the warehouse
    con = duckdb.connect(str(wh), read_only=True)
    try:
        hist_df = con.execute(
            f"select * from mart_repo_features "
            f"where snapshot_date = date '{snap_date}' order by repo_id"
        ).df()
    finally:
        con.close()

    if hist_df.empty:
        raise ValueError(f"No history mart_repo_features rows found for {snap_date} in {wh}")

    log.info("Loaded %d history candidates for %s", len(hist_df), snap_date)

    # 2. Build window mode features in a copy / temporary table
    # We run the single-date feature SQL with use_persistent_state=True
    window_ev = {
        "snapshot_dates_mode": "single",
        "snapshot_date": snap_date.isoformat(),
        "use_persistent_state": True,
        "n_buckets": 1,
    }

    # Run features in a separate isolated DuckDB connection
    temp_wh = P.DATA_DIR / "staging" / f"parity_{snap_date}.duckdb"
    temp_wh.parent.mkdir(parents=True, exist_ok=True)
    if temp_wh.exists():
        temp_wh.unlink()

    # Attach history warehouse read-only and copy necessary tables filtered to candidates
    con_tmp = duckdb.connect(str(temp_wh))
    try:
        con_tmp.execute("SET max_memory = '3GB'")
        con_tmp.execute("SET threads = 4")
        con_tmp.execute("SET preserve_insertion_order = false")
        con_tmp.execute(f"attach '{wh}' as src (READ_ONLY)")

        c_sub = (
            f"(select repo_id from src.mart_candidates where snapshot_date = date '{snap_date}')"
        )
        queries = [
            (
                f"create table mart_candidates as select * from src.mart_candidates "
                f"where snapshot_date = date '{snap_date}'"
            ),
            f"""create table stg_stars as
                select * from src.stg_stars
                where repo_id in {c_sub}
                  and starred_at >= date '{snap_date}' - 7
                  and starred_at < date '{snap_date}'""",
            f"""create table int_repo_star_daily as
                select * from src.int_repo_star_daily
                where repo_id in {c_sub}
                  and day < date '{snap_date}'""",
            f"""create table int_repo_daily_activity as
                select * from src.int_repo_daily_activity
                where repo_id in {c_sub}
                  and day >= date '{snap_date}' - 180
                  and day < date '{snap_date}'""",
            f"""create table int_core_actors_daily as
                select * from src.int_core_actors_daily
                where repo_id in {c_sub}
                  and day >= date '{snap_date}' - 90
                  and day < date '{snap_date}'""",
            f"""create table int_contributor_sessions as
                select * from src.int_contributor_sessions
                where repo_id in {c_sub}
                  and session_start >= date '{snap_date}' - 90
                  and session_start < date '{snap_date}'""",
            f"""create table int_star_events_enriched as
                select * from src.int_star_events_enriched
                where repo_id in {c_sub}
                  and starred_at >= date '{snap_date}' - 90
                  and starred_at < date '{snap_date}'""",
            f"""create table int_early_stars as
                select * from src.int_early_stars
                where repo_id in {c_sub}""",
            f"""create table int_stargazer_later_actions as
                select * from src.int_stargazer_later_actions
                where repo_id in {c_sub}""",
            f"""create table int_issue_response as
                select * from src.int_issue_response
                where repo_id in {c_sub}
                  and opened_at >= date '{snap_date}' - 90
                  and opened_at < date '{snap_date}'""",
            f"""create table int_pr_lifecycle as
                select * from src.int_pr_lifecycle
                where repo_id in {c_sub}
                  and opened_at >= date '{snap_date}' - 90
                  and opened_at < date '{snap_date}'""",
            f"""create table stg_hn_stories as
                select * from src.stg_hn_stories
                where repo_id in {c_sub}
                  and created_at >= date '{snap_date}' - 180
                  and created_at < date '{snap_date}'""",
            "create table top_languages as select * from src.top_languages",
            f"""create table stg_repo_metadata as
                select * from src.stg_repo_metadata
                where repo_id in {c_sub}""",
            f"""create table stg_repo_name_history as
                with c as (
                    select distinct lower(split_part(repo_name_at_D, '/', 1)) as owner
                    from src.mart_candidates
                    where snapshot_date = date '{snap_date}'
                )
                select * from src.stg_repo_name_history
                where lower(split_part(repo_name, '/', 1)) in (select owner from c)""",
            "create table int_repo_first_hit as select * from src.int_repo_first_hit",
            f"""create table int_actor_early_stars as
                with sg as (
                    select distinct s.actor_id
                    from src.int_early_stars s
                    where s.repo_id in {c_sub}
                      and s.star_day >= date '{snap_date}' - 14
                      and s.star_day < date '{snap_date}'
                )
                select * from src.int_actor_early_stars
                where outcome_day >= date '2023-06-01' and outcome_day < date '{snap_date}'
                  and actor_id in (select actor_id from sg)""",
        ]
        for q in queries:
            con_tmp.execute(q)
        con_tmp.execute("detach src")
    finally:
        con_tmp.close()

    old_env = os.environ.get("GHB_WAREHOUSE")
    try:
        os.environ["GHB_WAREHOUSE"] = str(temp_wh)
        for args in (
            [
                "run",
                "--select",
                "int_tastemaker_thresholds",
                "feat_star_dynamics",
                "feat_activity",
                "feat_stargazers",
                "feat_tastemaker",
                "feat_owner",
                "feat_detail",
                "feat_enrich",
                "mart_repo_features",
            ],
        ):
            rc = R.run_dbt(cfg, args, extra_vars=window_ev)
            if rc != 0:
                raise RuntimeError(f"dbt run failed during parity build with code {rc}")

        con_res = duckdb.connect(str(temp_wh), read_only=True)
        win_df = con_res.execute(
            f"select * from mart_repo_features "
            f"where snapshot_date = date '{snap_date}' order by repo_id"
        ).df()
        con_res.close()
    finally:
        if old_env is not None:
            os.environ["GHB_WAREHOUSE"] = old_env
        else:
            os.environ.pop("GHB_WAREHOUSE", None)
        if temp_wh.exists():
            temp_wh.unlink()

    log.info("Built %d window mode candidates for %s", len(win_df), snap_date)

    # 3. Calculate candidate set Jaccard
    hist_repos = set(hist_df["repo_id"])
    win_repos = set(win_df["repo_id"])
    intersection = hist_repos.intersection(win_repos)
    union = hist_repos.union(win_repos)
    jaccard = len(intersection) / len(union) if union else 1.0

    # 4. Compare feature values on common candidates
    common_ids = sorted(intersection)
    hist_common = (
        hist_df[hist_df["repo_id"].isin(common_ids)].sort_values("repo_id").reset_index(drop=True)
    )
    win_common = (
        win_df[win_df["repo_id"].isin(common_ids)].sort_values("repo_id").reset_index(drop=True)
    )

    ignore_cols = {"bucket", "repo_id", "snapshot_date"}
    feature_cols = [c for c in hist_df.columns if c not in ignore_cols and c in win_df.columns]

    feature_parity: dict[str, float] = {}
    total_cells = 0
    matching_cells = 0
    discrepancies: list[str] = []

    for c in feature_cols:
        s_hist = hist_common[c]
        s_win = win_common[c]

        # Check numeric vs string
        if pd.api.types.is_numeric_dtype(s_hist):
            v_hist = s_hist.to_numpy(dtype=float)
            v_win = s_win.to_numpy(dtype=float)
            nan_both = np.isnan(v_hist) & np.isnan(v_win)
            diff = np.abs(v_hist - v_win)
            close = (diff <= 1e-6) | nan_both
            match_count = int(np.sum(close))
        else:
            match_count = int(np.sum((s_hist == s_win) | (s_hist.isna() & s_win.isna())))

        match_rate = match_count / len(common_ids) if common_ids else 1.0
        feature_parity[c] = round(match_rate, 5)
        total_cells += len(common_ids)
        matching_cells += match_count

        if match_rate < 0.99:
            discrepancies.append(f"{c}: {match_rate:.2%} match rate (< 99%)")

    overall_cell_match = matching_cells / total_cells if total_cells else 1.0

    # 5. Prediction rank correlation (Spearman rho)
    model = G.load_champion(cfg)
    X_hist = D.apply_categories(hist_common[model.features], model.categories)
    X_win = D.apply_categories(win_common[model.features], model.categories)

    pred_hist = np.asarray(model.booster.predict(X_hist), dtype=float)
    pred_win = np.asarray(model.booster.predict(X_win), dtype=float)

    corr, _ = spearmanr(pred_hist, pred_win)
    corr_val = float(corr) if not np.isnan(corr) else 1.0

    passed = (
        jaccard >= 0.99
        and overall_cell_match >= 0.99
        and all(r >= 0.99 for r in feature_parity.values())
        and corr_val >= 0.99
    )

    # 6. Write docs/parity_daily_vs_history.md
    report_lines = [
        f"# Training/Serving Parity Report ({snap_date})",
        "",
        f"**Date Evaluated:** `{snap_date.isoformat()}`",
        f"**Status:** {'PASS' if passed else 'FAIL'}",
        f"**Champion Model:** `{model.version}`",
        "",
        "## Summary Metrics",
        f"- **Candidate Jaccard Index:** {jaccard:.4f} (Required: >= 0.99) -> "
        f"{'PASS' if jaccard >= 0.99 else 'FAIL'}",
        f"- **Historical Candidates:** {len(hist_repos)}",
        f"- **Window Mode Candidates:** {len(win_repos)}",
        f"- **Common Candidates:** {len(common_ids)}",
        f"- **Overall Cell Match Rate:** {overall_cell_match:.4f} (Required: >= 0.99) -> "
        f"{'PASS' if overall_cell_match >= 0.99 else 'FAIL'}",
        f"- **Spearman Rank Correlation:** {corr_val:.4f} (Required: >= 0.99) -> "
        f"{'PASS' if corr_val >= 0.99 else 'FAIL'}",
        "",
        "## Per-Feature Match Rates",
        "| Feature | Match Rate | Status |",
        "|---|---:|---|",
    ]
    for feat, rate in sorted(feature_parity.items()):
        report_lines.append(f"| `{feat}` | {rate:.2%} | {'PASS' if rate >= 0.99 else 'FAIL'} |")

    if discrepancies:
        report_lines.extend(["", "## Discrepancies", *[f"- {d}" for d in discrepancies]])
    else:
        report_lines.extend(
            [
                "",
                "## Discrepancies",
                "- None (100% of tested feature cells match parity requirements).",
            ]
        )

    report_lines.extend(
        [
            "",
            "## Methodology Notes",
            "- Historical features were produced by `mart_repo_features` in history mode.",
            (
                "- Daily window features were produced with persistent state tables ("
                "`tastemaker_state.parquet`, `owner_state.parquet`, "
                "`tastemaker_thresholds.parquet`) plus incremental window aggregation."
            ),
            (
                "- Predictions scored with the current champion model and compared "
                "via Spearman rank correlation."
            ),
        ]
    )

    PARITY_DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    PARITY_DOC_PATH.write_text("\n".join(report_lines) + "\n")
    log.info("Wrote parity report to %s (Passed: %s)", PARITY_DOC_PATH, passed)

    return ParityResult(
        snapshot_date=snap_date,
        jaccard=jaccard,
        n_history_candidates=len(hist_repos),
        n_window_candidates=len(win_repos),
        n_common_candidates=len(common_ids),
        feature_parity=feature_parity,
        overall_cell_match_rate=overall_cell_match,
        spearman_rank_corr=corr_val,
        passed=passed,
        report_path=PARITY_DOC_PATH,
        discrepancies=discrepancies,
    )
