"""Item-item co-star similarity reference index and daily lookup (Phase 11, §11.2).

- Reference index (weekly): repos with >= 50 stars in the last 365 days.
  Up to 2,000 most recent stargazers per repo, excluding bots and bulk starrers (>= 50 stars/day).
  Stores derived/similarity/reference_stargazers.parquet and reference_repo_sizes.parquet.
- Daily lookup: leaderboard repos stargazers joined to reference on actor_id;
  cosine = overlap / sqrt(n_a * n_b); top 5 with overlap >= 5, excluding repo itself and its forks.
"""

from __future__ import annotations

import math
import time
from datetime import date
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from breakout import paths as P
from breakout.config import Config, get_config
from breakout.duck import connect
from breakout.logging import get_logger

log = get_logger(__name__)

SIMILARITY_DIR = P.DATA_DIR / "derived" / "similarity"
REF_STARGAZERS_PARQUET = SIMILARITY_DIR / "reference_stargazers.parquet"
REF_REPO_SIZES_PARQUET = SIMILARITY_DIR / "reference_repo_sizes.parquet"


def compute_cosine_similarity(overlap: int, n_a: int, n_b: int) -> float:
    """Compute cosine similarity = overlap / sqrt(n_a * n_b).

    Guaranteed to be in [0.0, 1.0].
    """
    if overlap <= 0 or n_a <= 0 or n_b <= 0:
        return 0.0
    denom = math.sqrt(float(n_a) * float(n_b))
    if denom <= 0.0:
        return 0.0
    val = float(overlap) / denom
    return min(1.0, max(0.0, val))


def build_similarity_reference(
    cfg: Config | None = None,
    as_of: date | None = None,
    *,
    window_days: int = 365,
    min_stars: int = 50,
    max_stargazers: int = 2000,
    con: duckdb.DuckDBPyConnection | None = None,
) -> tuple[Path, Path, dict[str, Any]]:
    """Build similarity reference index from recent WatchEvents.

    Excludes known bots and bulk starrers (>= 50 stars/day).
    Saves to derived/similarity/reference_stargazers.parquet and reference_repo_sizes.parquet.
    """
    cfg = cfg or get_config(None)
    close_con = False
    if con is None:
        wh = P.DATA_DIR / "warehouse.duckdb"
        if not wh.exists():
            raise FileNotFoundError(f"Warehouse {wh} does not exist")
        con = connect(wh, read_only=True)
        close_con = True

    t0 = time.perf_counter()
    SIMILARITY_DIR.mkdir(parents=True, exist_ok=True)

    if as_of is None:
        try:
            row = con.execute("select max(starred_at)::date from stg_stars").fetchone()
            as_of_date = row[0] if (row and row[0]) else date.today()
        except Exception:
            as_of_date = date.today()
    else:
        as_of_date = as_of

    log.info(
        "Building similarity reference index as of %s (window_days=%d, min_stars=%d)...",
        as_of_date,
        window_days,
        min_stars,
    )

    # 1. Identify qualifying repos and filter out bots & bulk starrers
    sql_stargazers = f"""
    with qualifying_repos as (
        select repo_id
        from stg_stars
        where starred_at >= date '{as_of_date}' - interval '{window_days} days'
          and starred_at < date '{as_of_date}'
        group by repo_id
        having count(*) >= {min_stars}
    ),
    bot_actors as (
        select actor_id from stg_bot_actors
    ),
    bulk_starrers as (
        select actor_id, day
        from int_actor_daily_activity
        where n_stars_given >= 50
    ),
    eligible_stars as (
        select s.repo_id, s.actor_id, s.starred_at,
               row_number() over (partition by s.repo_id order by s.starred_at desc) as rn
        from stg_stars s
        join qualifying_repos q on s.repo_id = q.repo_id
        where s.starred_at >= date '{as_of_date}' - interval '{window_days} days'
          and s.starred_at < date '{as_of_date}'
          and s.actor_id not in (select actor_id from bot_actors)
          and not exists (
              select 1 from bulk_starrers b
              where b.actor_id = s.actor_id and b.day = s.starred_at::date
          )
    ),
    top_stargazers as (
        select repo_id, actor_id
        from eligible_stars
        where rn <= {max_stargazers}
        group by repo_id, actor_id
    )
    select * from top_stargazers
    """

    try:
        # Write directly to parquet using DuckDB native COPY (low memory, high speed)
        con.execute(
            f"COPY ({sql_stargazers}) TO '{REF_STARGAZERS_PARQUET}' (FORMAT PARQUET, COMPRESSION ZSTD)"
        )

        sql_sizes = f"""
        COPY (
            select repo_id, count(distinct actor_id) as n_stargazers
            from read_parquet('{REF_STARGAZERS_PARQUET}')
            group by repo_id
        ) TO '{REF_REPO_SIZES_PARQUET}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """
        con.execute(sql_sizes)

        duration = time.perf_counter() - t0
        stargazers_mb = REF_STARGAZERS_PARQUET.stat().st_size / (1024 * 1024)
        sizes_mb = REF_REPO_SIZES_PARQUET.stat().st_size / (1024 * 1024)

        row_sizes = con.execute(
            f"select count(*) from read_parquet('{REF_REPO_SIZES_PARQUET}')"
        ).fetchone()
        n_sizes = int(row_sizes[0]) if row_sizes else 0

        row_pairs = con.execute(
            f"select count(*) from read_parquet('{REF_STARGAZERS_PARQUET}')"
        ).fetchone()
        n_pairs = int(row_pairs[0]) if row_pairs else 0

        stats = {
            "n_reference_repos": int(n_sizes),
            "n_reference_stargazer_pairs": int(n_pairs),
            "duration_seconds": round(duration, 2),
            "stargazers_parquet_mb": round(stargazers_mb, 2),
            "sizes_parquet_mb": round(sizes_mb, 2),
        }
        log.info(
            "Built similarity reference: %d repos (%d pairs), %.2f MB in %.2f s",
            n_sizes,
            n_pairs,
            stargazers_mb,
            duration,
        )
        return REF_STARGAZERS_PARQUET, REF_REPO_SIZES_PARQUET, stats
    finally:
        if close_con:
            con.close()


def find_similar_repos(
    repo_ids: list[int],
    target_date: date | None = None,
    con: duckdb.DuckDBPyConnection | None = None,
    ref_stargazers_path: Path | None = None,
    ref_sizes_path: Path | None = None,
    top_k: int = 5,
    min_overlap: int = 5,
) -> dict[int, list[dict[str, Any]]]:
    """Find top similar repos for given candidate repo IDs using co-starring cosine similarity."""
    if not repo_ids:
        return {}

    p_stars = ref_stargazers_path or REF_STARGAZERS_PARQUET
    p_sizes = ref_sizes_path or REF_REPO_SIZES_PARQUET

    if not p_stars.exists() or not p_sizes.exists():
        log.warning("Reference similarity tables not found at %s. Returning empty.", p_stars)
        return {rid: [] for rid in repo_ids}

    close_con = False
    if con is None:
        wh = P.DATA_DIR / "warehouse.duckdb"
        if not wh.exists():
            log.warning("Warehouse %s not found. Returning empty.", wh)
            return {rid: [] for rid in repo_ids}
        con = connect(wh, read_only=True)
        close_con = True

    try:
        idl = ", ".join(str(i) for i in repo_ids)
        # Stargazers of target repos in window or warehouse
        query = f"""
        with ref_target as (
            select repo_id as target_repo_id, actor_id
            from read_parquet('{p_stars}')
            where repo_id in ({idl})
        ),
        early_target as (
            select repo_id as target_repo_id, actor_id
            from int_early_stars
            where repo_id in ({idl})
              and repo_id not in (select distinct target_repo_id from ref_target)
        ),
        target_stargazers as (
            select target_repo_id, actor_id from ref_target
            union all
            select target_repo_id, actor_id from early_target
        ),
        target_sizes as (
            select target_repo_id, count(distinct actor_id) as n_target
            from target_stargazers
            group by target_repo_id
        ),
        ref_stars as (
            select repo_id as ref_repo_id, actor_id
            from read_parquet('{p_stars}')
        ),
        ref_sizes as (
            select repo_id as ref_repo_id, n_stargazers as n_ref
            from read_parquet('{p_sizes}')
        ),
        co_stars as (
            select ts.target_repo_id, rs.ref_repo_id,
                   count(distinct ts.actor_id) as overlap
            from target_stargazers ts
            join ref_stars rs on ts.actor_id = rs.actor_id
            where ts.target_repo_id != rs.ref_repo_id
            group by ts.target_repo_id, rs.ref_repo_id
            having count(distinct ts.actor_id) >= {min_overlap}
        ),
        cosine_calc as (
            select c.target_repo_id, c.ref_repo_id, c.overlap,
                   c.overlap::double / sqrt(ts.n_target::double * rs.n_ref::double) as cosine,
                   row_number() over (
                       partition by c.target_repo_id
                       order by c.overlap::double / sqrt(ts.n_target::double * rs.n_ref::double) desc, c.overlap desc
                   ) as rank
            from co_stars c
            join target_sizes ts on c.target_repo_id = ts.target_repo_id
            join ref_sizes rs on c.ref_repo_id = rs.ref_repo_id
        ),
        latest_names as (
            select repo_id, repo_name,
                   row_number() over (partition by repo_id order by first_seen desc) as rn
            from stg_repo_name_history
        ),
        enriched as (
            select cc.target_repo_id, cc.ref_repo_id, cc.overlap,
                   round(cc.cosine, 4) as cosine,
                   coalesce(ln.repo_name, 'repo_id=' || cc.ref_repo_id) as similar_repo_name,
                   m.primary_language as similar_language
            from cosine_calc cc
            left join stg_repo_metadata m on m.repo_id = cc.ref_repo_id
            left join latest_names ln on ln.repo_id = cc.ref_repo_id and ln.rn = 1
            where cc.rank <= {top_k}
              and coalesce(m.parent_repo_id, 0) != cc.target_repo_id
        )
        select * from enriched order by target_repo_id, cosine desc
        """
        df = con.execute(query).df()
        res: dict[int, list[dict[str, Any]]] = {rid: [] for rid in repo_ids}
        for _, row in df.iterrows():
            tid = int(row["target_repo_id"])
            if tid in res:
                res[tid].append(
                    {
                        "repo_id": int(row["ref_repo_id"]),
                        "repo_name": str(row["similar_repo_name"]),
                        "overlap": int(row["overlap"]),
                        "cosine": float(row["cosine"]),
                        "language": row["similar_language"]
                        if pd.notna(row["similar_language"])
                        else None,
                        "html_url": f"https://github.com/{row['similar_repo_name']}"
                        if "/" in str(row["similar_repo_name"])
                        else f"https://github.com/repo_id={row['ref_repo_id']}",
                    }
                )
        return res
    except Exception as exc:
        log.warning("Could not execute find_similar_repos: %s", exc)
        return {rid: [] for rid in repo_ids}
    finally:
        if close_con:
            con.close()
