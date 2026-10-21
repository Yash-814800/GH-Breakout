"""Cohort retention analytics and historical reference bands (Phase 11, §11.3).

- Precomputes historical reference band for breakout_rel positives:
  stored in derived/reference/retention_reference.parquet.
- Exports weekly star cohorts (up to 12 weeks) x share who later forked, opened an issue/PR,
  or commented within 30 days (matured cohorts only).
"""

from __future__ import annotations

import time
from datetime import date
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from breakout import paths as P
from breakout.duck import connect
from breakout.logging import get_logger

log = get_logger(__name__)

REFERENCE_DIR = P.DATA_DIR / "derived" / "reference"
RETENTION_REF_PARQUET = REFERENCE_DIR / "retention_reference.parquet"


def compute_retention_reference(
    con: duckdb.DuckDBPyConnection | None = None,
    output_path: Path | None = None,
) -> Path:
    """Precompute median and IQR of 30d cohort retention metrics for historical breakout_rel positives.

    Segmented by repo age bucket (0-30d, 31-60d, 61-90d, 90+d).
    Saves to derived/reference/retention_reference.parquet.
    """
    out_p = output_path or RETENTION_REF_PARQUET
    out_p.parent.mkdir(parents=True, exist_ok=True)

    close_con = False
    if con is None:
        wh = P.DATA_DIR / "warehouse.duckdb"
        if not wh.exists():
            raise FileNotFoundError(f"Warehouse {wh} not found")
        con = connect(wh, read_only=True)
        close_con = True

    t0 = time.perf_counter()
    log.info("Computing historical cohort retention reference band...")

    sql = """
    with breakout_cohorts as (
        select c.repo_id, c.age_days,
               floor(c.age_days / 30.0)::integer as age_bucket,
               r.cohort_week, r.n_stargazers,
               r.share_fork_30d, r.share_issue_30d, r.share_pull_request_30d,
               r.share_comment_30d, r.share_any_30d
        from mart_candidates c
        join mart_labels l on l.repo_id = c.repo_id and l.snapshot_date = c.snapshot_date and l.breakout_rel
        join int_star_cohort_retention r on r.repo_id = c.repo_id and r.is_mature_30d
        where r.cohort_week <= c.snapshot_date and r.cohort_week >= c.snapshot_date - 90
    )
    select age_bucket,
           count(*) as n_cohorts,
           round(median(share_fork_30d), 4) as fork_median,
           round(quantile_cont(share_fork_30d, 0.25), 4) as fork_q1,
           round(quantile_cont(share_fork_30d, 0.75), 4) as fork_q3,

           round(median(share_issue_30d), 4) as issue_median,
           round(quantile_cont(share_issue_30d, 0.25), 4) as issue_q1,
           round(quantile_cont(share_issue_30d, 0.75), 4) as issue_q3,

           round(median(share_pull_request_30d), 4) as pr_median,
           round(quantile_cont(share_pull_request_30d, 0.25), 4) as pr_q1,
           round(quantile_cont(share_pull_request_30d, 0.75), 4) as pr_q3,

           round(median(share_comment_30d), 4) as comment_median,
           round(quantile_cont(share_comment_30d, 0.25), 4) as comment_q1,
           round(quantile_cont(share_comment_30d, 0.75), 4) as comment_q3,

           round(median(share_any_30d), 4) as any_median,
           round(quantile_cont(share_any_30d, 0.25), 4) as any_q1,
           round(quantile_cont(share_any_30d, 0.75), 4) as any_q3
    from breakout_cohorts
    group by age_bucket
    order by age_bucket
    """

    try:
        df = con.execute(sql).df()
        df.to_parquet(out_p, index=False)
        log.info(
            "Saved retention reference band (%d age buckets) to %s in %.2fs",
            len(df),
            out_p,
            time.perf_counter() - t0,
        )
        return out_p
    finally:
        if close_con:
            con.close()


def load_retention_reference(ref_path: Path | None = None) -> pd.DataFrame:
    """Load precomputed retention reference table."""
    p = ref_path or RETENTION_REF_PARQUET
    if p.exists():
        return pd.read_parquet(p)
    return pd.DataFrame()


def get_repo_cohort_retention(
    con: duckdb.DuckDBPyConnection,
    repo_ids: list[int],
    max_cohort_weeks: int = 12,
    as_of: date | None = None,
    ref_df: pd.DataFrame | None = None,
) -> dict[int, dict[str, Any]]:
    """Retrieve up to 12 weekly matured star cohorts for each repo with reference band comparison."""
    if not repo_ids:
        return {}

    idl = ", ".join(str(i) for i in repo_ids)
    date_filter = f"and cohort_week <= date '{as_of}'" if as_of else ""
    ref = ref_df if ref_df is not None else load_retention_reference()

    sql = f"""
    select repo_id, cohort_week, n_stargazers,
           round(share_fork_30d, 4) as share_fork_30d,
           round(share_issue_30d, 4) as share_issue_30d,
           round(share_pull_request_30d, 4) as share_pull_request_30d,
           round(share_comment_30d, 4) as share_comment_30d,
           round(share_any_30d, 4) as share_any_30d
    from int_star_cohort_retention
    where repo_id in ({idl})
      and is_mature_30d
      {date_filter}
    order by repo_id, cohort_week desc
    """

    res: dict[int, dict[str, Any]] = {
        rid: {"cohorts": [], "reference_comparison": None} for rid in repo_ids
    }

    try:
        df = con.execute(sql).df()
        for rid, group in df.groupby("repo_id"):
            rid_int = int(rid)
            cohort_rows = group.head(max_cohort_weeks).to_dict(orient="records")
            # Format dates as ISO string
            for c in cohort_rows:
                if isinstance(c["cohort_week"], date):
                    c["cohort_week"] = c["cohort_week"].isoformat()
                else:
                    c["cohort_week"] = str(c["cohort_week"])

            # Compute summary across matured cohorts
            avg_any = float(group["share_any_30d"].mean()) if not group.empty else 0.0

            comp_text = None
            ref_band = None
            if not ref.empty:
                # Default to age bucket 0 or 1
                ref_row = ref.iloc[0].to_dict()
                q1 = float(ref_row.get("any_q1", 0.0))
                q3 = float(ref_row.get("any_q3", 0.12))
                med = float(ref_row.get("any_median", 0.05))

                if avg_any >= q3:
                    eval_word = "above"
                elif avg_any < q1:
                    eval_word = "below"
                else:
                    eval_word = "within"

                comp_text = (
                    f"30-day interaction rate is {round(avg_any * 100, 1)}% "
                    f"({eval_word} the historical breakout IQR of {round(q1 * 100, 1)}%–{round(q3 * 100, 1)}%, median {round(med * 100, 1)}%)."
                )
                ref_band = {
                    "any_median": med,
                    "any_q1": q1,
                    "any_q3": q3,
                }

            res[rid_int] = {
                "cohorts": cohort_rows,
                "summary": {
                    "avg_interaction_rate": round(avg_any, 4),
                    "n_mature_cohorts": len(cohort_rows),
                },
                "reference_comparison": comp_text,
                "reference_band": ref_band,
            }
    except Exception as exc:
        log.warning("Could not extract repo cohort retention: %s", exc)

    return res
