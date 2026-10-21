"""Signal extractors for suspicious growth (fake star patterns).

Signals computed over stars in [D-14, D):
- s_new_accounts: share of stargazers with estimated account age < 30 days (and < 7 days)
- s_inactive: share with zero activity in the 90 days before their star
- s_bulk: share who starred >= 50 repos that UTC day
- s_burst: max share of the window's stars landing in a single hour (+ CV regularity)
- s_lockstep: share of stargazers who co-starred >= 3 of the same other repos within +-24h
- s_no_engagement: 1 - min(1, engagement_events / (0.05 * stars_14d))
"""

from __future__ import annotations

from datetime import date

import duckdb
import pandas as pd

from breakout.logging import get_logger

log = get_logger(__name__)


def compute_burst_signals(
    con: duckdb.DuckDBPyConnection,
    target_date: date,
    repo_ids: list[int] | None = None,
) -> pd.DataFrame:
    """Compute hourly burst max share and inter-arrival regularity in [D-14, D)."""
    filter_repo = ""
    if repo_ids is not None:
        if not repo_ids:
            return pd.DataFrame(columns=["repo_id", "s_burst", "burst_regularity"])
        idl = ", ".join(str(i) for i in repo_ids)
        filter_repo = f"and s.repo_id in ({idl})"

    # Query top hour and coefficient of variation of inter-arrival times
    sql = f"""
    with window_stars as (
        select repo_id, actor_id, starred_at,
               date_trunc('hour', starred_at) as star_hour
        from stg_stars s
        where starred_at >= date '{target_date}' - interval '14 days'
          and starred_at < date '{target_date}'
          {filter_repo}
    ),
    hour_counts as (
        select repo_id, star_hour, count(*) as hour_stars
        from window_stars
        group by repo_id, star_hour
    ),
    repo_totals as (
        select repo_id, sum(hour_stars) as total_window_stars, max(hour_stars) as max_hour_stars
        from hour_counts
        group by repo_id
    ),
    top_hours as (
        select h.repo_id, h.star_hour, h.hour_stars
        from hour_counts h
        join repo_totals t on h.repo_id = t.repo_id and h.hour_stars = t.max_hour_stars
    ),
    top_hour_intervals as (
        select ws.repo_id,
               epoch(ws.starred_at) - epoch(lag(ws.starred_at) over (partition by ws.repo_id order by ws.starred_at)) as dt_sec
        from window_stars ws
        join top_hours th on ws.repo_id = th.repo_id and ws.star_hour = th.star_hour
    ),
    cv_calc as (
        select repo_id,
               stddev_samp(dt_sec) as sd_dt,
               avg(dt_sec) as mean_dt,
               stddev_samp(dt_sec) / nullif(avg(dt_sec), 0.0) as cv
        from top_hour_intervals
        where dt_sec is not null
        group by repo_id
    )
    select t.repo_id,
           round(t.max_hour_stars::double / greatest(t.total_window_stars, 1), 4) as s_burst,
           coalesce(c.cv < 0.5 and t.max_hour_stars >= 5, false) as burst_regularity
    from repo_totals t
    left join cv_calc c using (repo_id)
    """
    try:
        return con.execute(sql).df()
    except Exception as exc:
        log.warning("Could not compute burst signals from stg_stars: %s", exc)
        return pd.DataFrame(columns=["repo_id", "s_burst", "burst_regularity"])


def compute_lockstep_signals(
    con: duckdb.DuckDBPyConnection,
    target_date: date,
    repo_ids: list[int] | None = None,
    max_stargazers_per_repo: int = 5000,
) -> pd.DataFrame:
    """Compute lockstep ring co-starring signals in [D-14, D).

    Share of stargazers who also starred >= 3 of the same other repos within +-24h
    of starring this repo.
    """
    filter_repo = ""
    if repo_ids is not None:
        if not repo_ids:
            return pd.DataFrame(columns=["repo_id", "s_lockstep"])
        idl = ", ".join(str(i) for i in repo_ids)
        filter_repo = f"and repo_id in ({idl})"

    sql = f"""
    with cand_stars as (
        select repo_id, actor_id, starred_at
        from (
            select repo_id, actor_id, starred_at,
                   row_number() over (partition by repo_id order by starred_at desc) as rn
            from stg_stars
            where starred_at >= date '{target_date}' - interval '14 days'
              and starred_at < date '{target_date}'
              {filter_repo}
        )
        where rn <= {max_stargazers_per_repo}
    ),
    stargazer_counts as (
        select repo_id, count(distinct actor_id) as n_stargazers
        from cand_stars
        group by repo_id
    ),
    other_stars as (
        select cs.repo_id as target_repo_id, cs.actor_id, s.repo_id as other_repo_id
        from cand_stars cs
        join stg_stars s on s.actor_id = cs.actor_id
                        and s.repo_id != cs.repo_id
                        and s.starred_at >= cs.starred_at - interval '24 hours'
                        and s.starred_at <= cs.starred_at + interval '24 hours'
    ),
    co_starrers as (
        select o1.target_repo_id, o1.actor_id, count(distinct o1.other_repo_id) as n_shared
        from other_stars o1
        join other_stars o2 on o1.other_repo_id = o2.other_repo_id
                           and o1.target_repo_id = o2.target_repo_id
                           and o1.actor_id != o2.actor_id
        group by o1.target_repo_id, o1.actor_id
        having count(distinct o1.other_repo_id) >= 3
    ),
    ring_counts as (
        select target_repo_id as repo_id, count(distinct actor_id) as n_lockstep
        from co_starrers
        group by target_repo_id
    )
    select sc.repo_id,
           coalesce(round(rc.n_lockstep::double / nullif(sc.n_stargazers, 0), 4), 0.0) as s_lockstep
    from stargazer_counts sc
    left join ring_counts rc using (repo_id)
    """
    try:
        return con.execute(sql).df()
    except Exception as exc:
        log.warning("Could not compute lockstep signals: %s", exc)
        return pd.DataFrame(columns=["repo_id", "s_lockstep"])


def extract_candidate_signals(
    con: duckdb.DuckDBPyConnection,
    target_date: date | None = None,
    repo_ids: list[int] | None = None,
) -> pd.DataFrame:
    """Extract candidate signals from warehouse marts / feature tables."""
    where_clauses: list[str] = []
    if target_date is not None:
        where_clauses.append(f"c.snapshot_date = date '{target_date}'")
    if repo_ids is not None and len(repo_ids) > 0:
        idl = ", ".join(str(i) for i in repo_ids)
        where_clauses.append(f"c.repo_id in ({idl})")

    filter_sql = f"where {' and '.join(where_clauses)}" if where_clauses else ""

    sql = f"""
    with base as (
        select c.repo_id, c.snapshot_date, c.stars_14d, c.repo_name_at_D as repo_name,
               coalesce(sg.sg_share_account_lt_30d, 0.0) as s_new_accounts,
               coalesce(sg.sg_share_zero_prior_activity, 0.0) as s_inactive,
               coalesce(sg.sg_share_bulk_starrers, 0.0) as s_bulk,
               coalesce(sd.star_max_hour_share_7d, 0.0) as s_burst,
               0.0 as s_lockstep,
               1.0 - least(1.0, (
                   coalesce(fa.forks_14d, 0) +
                   coalesce(fa.issue_events_14d, 0) +
                   coalesce(fa.comment_events_14d, 0) +
                   coalesce(fa.pr_events_14d, 0)
               )::double / (0.05 * greatest(c.stars_14d, 1))) as s_no_engagement
        from mart_candidates c
        left join feat_stargazers sg on sg.repo_id = c.repo_id and sg.snapshot_date = c.snapshot_date
        left join feat_star_dynamics sd on sd.repo_id = c.repo_id and sd.snapshot_date = c.snapshot_date
        left join feat_activity fa on fa.repo_id = c.repo_id and fa.snapshot_date = c.snapshot_date
        {filter_sql}
    )
    select * from base
    """
    df = con.execute(sql).df()

    # If single snapshot and candidate count is bounded, compute lockstep & burst
    if target_date is not None and len(df) > 0 and len(df) <= 2000:
        try:
            rids = [int(r) for r in df["repo_id"]]
            burst_df = compute_burst_signals(con, target_date, rids)
            if not burst_df.empty and "s_burst" in burst_df.columns:
                df = df.drop(columns=["s_burst"]).merge(
                    burst_df[["repo_id", "s_burst", "burst_regularity"]], on="repo_id", how="left"
                )
                df["s_burst"] = df["s_burst"].fillna(0.0)
                df["burst_regularity"] = df["burst_regularity"].fillna(False)

            lock_df = compute_lockstep_signals(con, target_date, rids)
            if not lock_df.empty and "s_lockstep" in lock_df.columns:
                df = df.drop(columns=["s_lockstep"]).merge(
                    lock_df[["repo_id", "s_lockstep"]], on="repo_id", how="left"
                )
                df["s_lockstep"] = df["s_lockstep"].fillna(0.0)
        except Exception as exc:
            log.debug("Live window burst/lockstep calculation skipped: %s", exc)

    return df
