"""Persistent state tables for tastemaker and owner features (§9.1, §9.2 Step 6).

Maintains:
- `derived/state/tastemaker_state.parquet`: per actor `actor_id, early_stars_known, hits_known, as_of`
- `derived/state/owner_state.parquet`: per owner prefix `owner, prior_repos_seen, prior_breakouts, as_of`
- `derived/state/tastemaker_thresholds.parquet`: monthly top-1% score thresholds

In history mode, feature models compute from scratch over all history.
In daily window mode, feature models read persistent state + window increment.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import duckdb

from breakout import paths as P
from breakout.config import Config
from breakout.duck import connect
from breakout.logging import get_logger

log = get_logger(__name__)

STATE_DIR = P.DERIVED_DIR / "state"
TASTEMAKER_STATE_PATH = STATE_DIR / "tastemaker_state.parquet"
OWNER_STATE_PATH = STATE_DIR / "owner_state.parquet"
TASTEMAKER_THRESHOLDS_PATH = STATE_DIR / "tastemaker_thresholds.parquet"
HF_PREFIX = "state"


def state_dir() -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR


def warehouse_path() -> Path:
    return Path(os.environ.get("GHB_WAREHOUSE") or P.WAREHOUSE)


def build_state(
    cfg: Config,
    as_of: date,
    warehouse: Path | None = None,
    upload: bool = False,
) -> tuple[Path, Path, Path]:
    """Initialize persistent state tables from the historical warehouse as of ``as_of``."""
    wh = warehouse or warehouse_path()
    if not wh.exists():
        raise FileNotFoundError(f"Warehouse not found at {wh}")

    state_dir()
    con = connect(wh, read_only=True)
    con.execute("SET memory_limit='1500MB'")
    con.execute("SET threads=1")

    log.info("Building persistent state tables as of %s from %s", as_of, wh)

    # 1. Tastemaker state
    tm_out = TASTEMAKER_STATE_PATH
    tm_tmp = tm_out.with_suffix(".tmp")
    log.info("Computing tastemaker_state as of %s...", as_of)
    con.execute(
        f"""
        copy (
            select actor_id,
                   early_stars_known,
                   hits_known,
                   date '{as_of}' as as_of
            from int_actor_early_cum
            where outcome_day < date '{as_of}'
            qualify row_number() over (partition by actor_id order by outcome_day desc) = 1
            order by actor_id
        ) to '{tm_tmp}' (format parquet, compression zstd)
        """
    )
    tm_tmp.replace(tm_out)
    n_tm = con.execute(f"select count(*) from read_parquet('{tm_out}')").fetchone()[0]  # type: ignore[index]
    log.info("Wrote %s with %d actors", tm_out, n_tm)

    # 2. Owner state
    own_out = OWNER_STATE_PATH
    own_tmp = own_out.with_suffix(".tmp")
    log.info("Computing owner_state as of %s...", as_of)
    con.execute(
        f"""
        copy (
            with h as (
                select repo_id, lower(split_part(repo_name, '/', 1)) as owner, min(first_seen) as first_seen
                from stg_repo_name_history
                where first_seen < date '{as_of}'
                group by 1, 2
            ),
            hits as (
                select repo_id, min(first_hit_outcome_day) as first_hit_outcome_day
                from int_repo_first_hit
                where first_hit_outcome_day < date '{as_of}'
                group by 1
            )
            select h.owner,
                   count(distinct h.repo_id)::integer as prior_repos_seen,
                   count(distinct hits.repo_id)::integer as prior_breakouts,
                   date '{as_of}' as as_of
            from h
            left join hits on hits.repo_id = h.repo_id
            where h.owner is not null and h.owner <> ''
            group by 1
            order by owner
        ) to '{own_tmp}' (format parquet, compression zstd)
        """
    )
    own_tmp.replace(own_out)
    n_own = con.execute(f"select count(*) from read_parquet('{own_out}')").fetchone()[0]  # type: ignore[index]
    log.info("Wrote %s with %d owners", own_out, n_own)

    # 3. Tastemaker thresholds
    thresh_out = TASTEMAKER_THRESHOLDS_PATH
    thresh_tmp = thresh_out.with_suffix(".tmp")
    log.info("Computing tastemaker_thresholds as of %s...", as_of)
    con.execute(
        f"""
        copy (
            select month, score_threshold, n_actors
            from int_tastemaker_thresholds
            where month <= date '{as_of}'
            order by month
        ) to '{thresh_tmp}' (format parquet, compression zstd)
        """
    )
    thresh_tmp.replace(thresh_out)
    n_thresh = con.execute(f"select count(*) from read_parquet('{thresh_out}')").fetchone()[0]  # type: ignore[index]
    log.info("Wrote %s with %d monthly thresholds", thresh_out, n_thresh)

    con.close()

    if upload:
        upload_state(cfg)

    return tm_out, own_out, thresh_out


def update_state(
    cfg: Config,
    target_date: date,
    warehouse: Path | None = None,
    con: duckdb.DuckDBPyConnection | None = None,
    upload: bool = False,
) -> tuple[Path, Path, Path]:
    """Incremental state update (Step 6 of daily pipeline).

    Updates state tables with outcomes that matured in ``[state.as_of, target_date)``.
    """
    out_dir = state_dir()
    if not TASTEMAKER_STATE_PATH.exists() or not OWNER_STATE_PATH.exists():
        raise FileNotFoundError(
            f"State tables missing in {out_dir}. Run `breakout build state --as-of <date>` first."
        )

    close_con = False
    if con is None:
        wh = warehouse or warehouse_path()
        con = connect(wh, read_only=False)
        close_con = True

    try:
        row = con.execute(
            f"select max(as_of) from read_parquet('{TASTEMAKER_STATE_PATH}')"
        ).fetchone()
        cur_as_of = row[0] if row is not None else None
        if cur_as_of is None:
            raise ValueError("tastemaker_state has no as_of date")
        if isinstance(cur_as_of, str):
            cur_as_of = date.fromisoformat(cur_as_of)

        if cur_as_of >= target_date:
            log.info("State is already current as of %s >= target %s", cur_as_of, target_date)
            return TASTEMAKER_STATE_PATH, OWNER_STATE_PATH, TASTEMAKER_THRESHOLDS_PATH

        log.info("Updating state from %s to %s", cur_as_of, target_date)

        # 1. Update Tastemaker state
        tm_tmp = TASTEMAKER_STATE_PATH.with_suffix(".tmp")
        con.execute(
            f"""
            copy (
                with existing as (
                    select actor_id, early_stars_known, hits_known
                    from read_parquet('{TASTEMAKER_STATE_PATH}')
                ),
                inc as (
                    select actor_id,
                           count(*)::integer as inc_n,
                           count(*) filter (where is_hit)::integer as inc_h
                    from int_actor_early_stars
                    where outcome_day >= date '{cur_as_of}' and outcome_day < date '{target_date}'
                    group by 1
                )
                select coalesce(e.actor_id, i.actor_id) as actor_id,
                       (coalesce(e.early_stars_known, 0) + coalesce(i.inc_n, 0))::integer as early_stars_known,
                       (coalesce(e.hits_known, 0) + coalesce(i.inc_h, 0))::integer as hits_known,
                       date '{target_date}' as as_of
                from existing e
                full outer join inc i on e.actor_id = i.actor_id
                order by 1
            ) to '{tm_tmp}' (format parquet, compression zstd)
            """
        )
        tm_tmp.replace(TASTEMAKER_STATE_PATH)

        # 2. Update Owner state
        own_tmp = OWNER_STATE_PATH.with_suffix(".tmp")
        con.execute(
            f"""
            copy (
                with existing as (
                    select owner, prior_repos_seen, prior_breakouts
                    from read_parquet('{OWNER_STATE_PATH}')
                ),
                inc_repos as (
                    select lower(split_part(repo_name, '/', 1)) as owner,
                           count(distinct repo_id)::integer as inc_seen
                    from stg_repo_name_history
                    where first_seen >= date '{cur_as_of}' and first_seen < date '{target_date}'
                    group by 1
                ),
                inc_hits as (
                    select lower(split_part(h.repo_name, '/', 1)) as owner,
                           count(distinct f.repo_id)::integer as inc_breakouts
                    from int_repo_first_hit f
                    join stg_repo_name_history h using (repo_id)
                    where f.first_hit_outcome_day >= date '{cur_as_of}' and f.first_hit_outcome_day < date '{target_date}'
                    group by 1
                ),
                inc as (
                    select coalesce(r.owner, h.owner) as owner,
                           coalesce(r.inc_seen, 0)::integer as inc_seen,
                           coalesce(h.inc_breakouts, 0)::integer as inc_breakouts
                    from inc_repos r
                    full outer join inc_hits h on r.owner = h.owner
                )
                select coalesce(e.owner, i.owner) as owner,
                       (coalesce(e.prior_repos_seen, 0) + coalesce(i.inc_seen, 0))::integer as prior_repos_seen,
                       (coalesce(e.prior_breakouts, 0) + coalesce(i.inc_breakouts, 0))::integer as prior_breakouts,
                       date '{target_date}' as as_of
                from existing e
                full outer join inc i on e.owner = i.owner
                where coalesce(e.owner, i.owner) is not null and coalesce(e.owner, i.owner) <> ''
                order by 1
            ) to '{own_tmp}' (format parquet, compression zstd)
            """
        )
        own_tmp.replace(OWNER_STATE_PATH)

        # 3. Update thresholds if a month boundary passed
        m0 = date(cur_as_of.year, cur_as_of.month, 1)
        m1 = date(target_date.year, target_date.month, 1)
        if m1 > m0 and TASTEMAKER_THRESHOLDS_PATH.exists():
            thresh_tmp = TASTEMAKER_THRESHOLDS_PATH.with_suffix(".tmp")
            # compute threshold for m1
            # Top 1% threshold among actors with >= 5 known early stars as of target_date
            con.execute(
                f"""
                copy (
                    with existing as (
                        select month, score_threshold, n_actors
                        from read_parquet('{TASTEMAKER_THRESHOLDS_PATH}')
                        where month < date '{m1}'
                    ),
                    actors as (
                        select actor_id,
                               early_stars_known as n,
                               hits_known as h,
                               (hits_known + {cfg.features.tastemaker.alpha})
                                 / (early_stars_known + {cfg.features.tastemaker.alpha} + {cfg.features.tastemaker.beta}) as score
                        from read_parquet('{TASTEMAKER_STATE_PATH}')
                        where early_stars_known >= {cfg.features.tastemaker.min_known}
                    ),
                    counted as (
                        select score, count(*)::bigint as n_with_score
                        from actors
                        group by 1
                    ),
                    ranked as (
                        select score, n_with_score,
                               sum(n_with_score) over (order by score) as cum_actors,
                               sum(n_with_score) over () as total_actors
                        from counted
                    ),
                    new_month as (
                        select date '{m1}' as month,
                               min(score) filter (where cum_actors >= (1.0 - {cfg.features.tastemaker.top_quantile}) * total_actors) as score_threshold,
                               max(total_actors)::bigint as n_actors
                        from ranked
                    )
                    select * from existing
                    union all
                    select * from new_month where n_actors is not null and n_actors > 0
                    order by month
                ) to '{thresh_tmp}' (format parquet, compression zstd)
                """
            )
            thresh_tmp.replace(TASTEMAKER_THRESHOLDS_PATH)

    finally:
        if close_con:
            con.close()

    if upload:
        upload_state(cfg)

    return TASTEMAKER_STATE_PATH, OWNER_STATE_PATH, TASTEMAKER_THRESHOLDS_PATH


def upload_state(cfg: Config) -> list[str]:
    """Upload state files to the derived repo under state/."""
    from breakout.lake import hf

    api = hf.get_api()
    items = []
    for p in (TASTEMAKER_STATE_PATH, OWNER_STATE_PATH, TASTEMAKER_THRESHOLDS_PATH):
        if p.exists():
            items.append(hf.UploadItem(p, f"{HF_PREFIX}/{p.name}"))
    if not items:
        return []
    res = hf.put_small_files(api, cfg, "derived", items, "Update persistent state tables")
    return [res] if res else []


def pull_state(cfg: Config) -> tuple[Path, Path, Path]:
    """Download state files from the derived repo."""
    from breakout.lake import hf

    api = hf.get_api()
    dest = state_dir()
    files = ["tastemaker_state.parquet", "owner_state.parquet", "tastemaker_thresholds.parquet"]
    hf.download_files(api, cfg, "derived", [f"{HF_PREFIX}/{f}" for f in files], dest)
    # move from dest/state/* to dest/* if downloaded with prefix
    for f in files:
        sub = dest / HF_PREFIX / f
        target = dest / f
        if sub.exists() and not target.exists():
            sub.replace(target)
    return TASTEMAKER_STATE_PATH, OWNER_STATE_PATH, TASTEMAKER_THRESHOLDS_PATH
